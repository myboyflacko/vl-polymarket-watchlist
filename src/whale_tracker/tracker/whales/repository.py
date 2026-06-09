from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from whale_tracker.core.db.engine import database_session
from whale_tracker.core.time import ensure_utc
from whale_tracker.tracker.whales.domain import (
    LeaderboardObservation,
    TrackedWhale,
    TrackedWhales,
    Whale,
    WhaleIdentity,
    Whales,
)
from whale_tracker.tracker.whales.models import (
    PolymarketWhale,
    TrackedWhale as TrackedWhaleRow,
    WhaleObservation,
    WhaleRun,
)


DEFAULT_TRACKED_WHALE_FILTER_PROFILE = "leaderboard_streak_3_v1"
DEFAULT_TRACKED_WHALE_STREAK_RUNS = 3


def get_latest_discovery_run_id() -> str | None:
    return _latest_completed_run_id()


def get_latest_tracked_whale_run_id() -> str | None:
    with database_session() as session:
        run_id = session.scalar(
            select(TrackedWhaleRow.run_id)
            .join(WhaleRun, WhaleRun.run_id == TrackedWhaleRow.run_id)
            .order_by(WhaleRun.generated_at.desc(), TrackedWhaleRow.run_id.desc())
            .limit(1)
        )

    return run_id


def list_whale_observations(run_id: str | None = None) -> Whales:
    actual_run_id = run_id or get_latest_discovery_run_id()
    if actual_run_id is None:
        return _empty_whales()

    with database_session() as session:
        run = session.get(WhaleRun, actual_run_id)
        if run is None:
            return _empty_whales()

        rows = list(
            session.execute(
                select(WhaleObservation, PolymarketWhale)
                .join(PolymarketWhale, WhaleObservation.whale_id == PolymarketWhale.id)
                .where(WhaleObservation.run_id == actual_run_id)
                .order_by(WhaleObservation.id)
            )
        )

    return Whales(
        whales=[
            _whale_from_observation(observation=observation, identity=identity)
            for observation, identity in rows
        ],
        candidate_wallet_count=run.checked_wallet_count,
        checked_wallet_count=run.checked_wallet_count,
        generated_at=run.generated_at,
        profile_version=run.profile_version,
    )


def list_tracked_whale_wallets(run_id: str | None = None) -> list[str]:
    actual_run_id = run_id or get_latest_discovery_run_id()
    if actual_run_id is None:
        return []

    with database_session() as session:
        return list(
            session.scalars(
                select(PolymarketWhale.proxy_wallet)
                .join(
                    TrackedWhaleRow,
                    TrackedWhaleRow.whale_id == PolymarketWhale.id,
                )
                .where(TrackedWhaleRow.run_id == actual_run_id)
                .order_by(TrackedWhaleRow.id)
            )
        )


def list_tracked_whales(run_id: str | None = None) -> TrackedWhales:
    actual_run_id = run_id or get_latest_discovery_run_id()
    if actual_run_id is None:
        return _empty_tracked_whales(run_id="")

    with database_session() as session:
        run = session.get(WhaleRun, actual_run_id)
        if run is None:
            return _empty_tracked_whales(run_id=actual_run_id)

        rows = list(
            session.execute(
                select(TrackedWhaleRow, PolymarketWhale)
                .join(
                    PolymarketWhale,
                    TrackedWhaleRow.whale_id == PolymarketWhale.id,
                )
                .where(TrackedWhaleRow.run_id == actual_run_id)
                .order_by(TrackedWhaleRow.id)
            )
        )

    whales = [
        _tracked_whale_from_row(run_id=actual_run_id, row=row, identity=identity)
        for row, identity in rows
    ]
    filter_profile = (
        whales[0].filter_profile if whales else DEFAULT_TRACKED_WHALE_FILTER_PROFILE
    )
    return TrackedWhales(
        whales=whales,
        run_id=actual_run_id,
        generated_at=run.generated_at,
        filter_profile=filter_profile,
    )


def persist_whale_run(
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    whales: Whales,
) -> None:
    started_at = ensure_utc(started_at)
    finished_at = ensure_utc(finished_at)
    generated_at = ensure_utc(whales.generated_at)

    with database_session() as session:
        session.add(
            WhaleRun(
                run_id=run_id,
                status="completed",
                profile_version=whales.profile_version,
                started_at=started_at,
                finished_at=finished_at,
                generated_at=generated_at,
                checked_wallet_count=whales.checked_wallet_count,
                observed_wallet_count=whales.wallet_count,
                tracked_wallet_count=0,
            )
        )
        session.flush()
        whale_ids = _upsert_whales(
            session=session,
            seen_at=generated_at,
            whales=whales.whales,
        )
        _upsert_whale_observations(
            session=session,
            run_id=run_id,
            generated_at=generated_at,
            whales=whales.whales,
            whale_ids=whale_ids,
        )
        session.commit()


def persist_tracked_whales(
    *,
    run_id: str,
    filter_profile: str = DEFAULT_TRACKED_WHALE_FILTER_PROFILE,
    required_consecutive_runs: int = DEFAULT_TRACKED_WHALE_STREAK_RUNS,
) -> TrackedWhales:
    with database_session() as session:
        run = session.get(WhaleRun, run_id)
        if run is None:
            raise ValueError(f"Whale run not found: {run_id}")

        recent_runs = list(
            session.scalars(
                select(WhaleRun)
                .where(
                    WhaleRun.status == "completed",
                    WhaleRun.generated_at <= run.generated_at,
                )
                .order_by(WhaleRun.generated_at.desc(), WhaleRun.run_id.desc())
                .limit(required_consecutive_runs)
            )
        )
        recent_run_ids = [entry.run_id for entry in recent_runs]
        tracked_entries: list[tuple[WhaleObservation, PolymarketWhale]] = []

        if len(recent_run_ids) == required_consecutive_runs and run_id in recent_run_ids:
            wallet_run_counts = _wallet_run_counts(
                session=session,
                run_ids=recent_run_ids,
            )
            current_rows = list(
                session.execute(
                    select(WhaleObservation, PolymarketWhale)
                    .join(
                        PolymarketWhale,
                        WhaleObservation.whale_id == PolymarketWhale.id,
                    )
                    .where(WhaleObservation.run_id == run_id)
                    .order_by(WhaleObservation.id)
                )
            )
            tracked_entries = [
                (observation, identity)
                for observation, identity in current_rows
                if wallet_run_counts.get(identity.proxy_wallet, 0)
                == required_consecutive_runs
            ]

        rows = [
            {
                "run_id": run_id,
                "whale_id": observation.whale_id,
                "filter_profile": filter_profile,
                "consecutive_runs": required_consecutive_runs,
                "candidate_source": observation.candidate_source,
                "pnl_rank": observation.pnl_rank,
                "volume_rank": observation.volume_rank,
                "leaderboard_pnl": observation.leaderboard_pnl,
                "leaderboard_volume": observation.leaderboard_volume,
                "generated_at": ensure_utc(run.generated_at),
            }
            for observation, _identity in tracked_entries
        ]
        if rows:
            statement = insert(TrackedWhaleRow).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        TrackedWhaleRow.run_id,
                        TrackedWhaleRow.whale_id,
                        TrackedWhaleRow.filter_profile,
                    ],
                    set_={
                        "consecutive_runs": statement.excluded.consecutive_runs,
                        "candidate_source": statement.excluded.candidate_source,
                        "pnl_rank": statement.excluded.pnl_rank,
                        "volume_rank": statement.excluded.volume_rank,
                        "leaderboard_pnl": statement.excluded.leaderboard_pnl,
                        "leaderboard_volume": statement.excluded.leaderboard_volume,
                        "generated_at": statement.excluded.generated_at,
                    },
                )
            )

        session.execute(
            update(WhaleRun)
            .where(WhaleRun.run_id == run_id)
            .values(tracked_wallet_count=len(rows))
        )
        session.commit()

    return list_tracked_whales(run_id)


def _latest_completed_run_id() -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(WhaleRun)
            .where(WhaleRun.status == "completed")
            .order_by(WhaleRun.generated_at.desc(), WhaleRun.run_id.desc())
            .limit(1)
        )

    return run.run_id if run is not None else None


def _empty_whales() -> Whales:
    return Whales(
        whales=[],
        candidate_wallet_count=0,
        checked_wallet_count=0,
        generated_at=datetime.min.replace(tzinfo=UTC),
        profile_version="unknown",
    )


def _empty_tracked_whales(*, run_id: str) -> TrackedWhales:
    return TrackedWhales(
        whales=[],
        run_id=run_id,
        generated_at=datetime.min.replace(tzinfo=UTC),
        filter_profile=DEFAULT_TRACKED_WHALE_FILTER_PROFILE,
    )


def _upsert_whales(
    *,
    session: Session,
    seen_at: datetime,
    whales: Iterable[Whale],
) -> dict[str, int]:
    rows = [
        {
            "proxy_wallet": whale.proxy_wallet,
            "identity": whale.identity.model_dump(mode="json"),
            "first_seen_at": seen_at,
            "last_seen_at": seen_at,
        }
        for whale in whales
    ]
    if not rows:
        return {}

    statement = insert(PolymarketWhale).values(rows)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[PolymarketWhale.proxy_wallet],
            set_={
                "identity": statement.excluded.identity,
                "last_seen_at": statement.excluded.last_seen_at,
            },
        )
    )
    return dict(
        session.execute(
            select(PolymarketWhale.proxy_wallet, PolymarketWhale.id).where(
                PolymarketWhale.proxy_wallet.in_(
                    [row["proxy_wallet"] for row in rows]
                )
            )
        ).all()
    )


def _upsert_whale_observations(
    *,
    session: Session,
    run_id: str,
    generated_at: datetime,
    whales: list[Whale],
    whale_ids: dict[str, int],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "whale_id": whale_ids[whale.proxy_wallet],
            "candidate_source": whale.observation.candidate_source,
            "pnl_rank": whale.observation.pnl_rank,
            "volume_rank": whale.observation.volume_rank,
            "leaderboard_pnl": whale.observation.leaderboard_pnl,
            "leaderboard_volume": whale.observation.leaderboard_volume,
            "generated_at": generated_at,
        }
        for whale in whales
        if whale.proxy_wallet in whale_ids
    ]
    if not rows:
        return

    statement = insert(WhaleObservation).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "whale_id"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[WhaleObservation.run_id, WhaleObservation.whale_id],
            set_=update_columns,
        )
    )


def _wallet_run_counts(*, session: Session, run_ids: list[str]) -> dict[str, int]:
    rows = session.execute(
        select(PolymarketWhale.proxy_wallet, WhaleObservation.run_id)
        .join(WhaleObservation, WhaleObservation.whale_id == PolymarketWhale.id)
        .where(WhaleObservation.run_id.in_(run_ids))
    )
    wallet_run_ids: dict[str, set[str]] = {}
    for wallet, seen_run_id in rows:
        wallet_run_ids.setdefault(wallet, set()).add(seen_run_id)

    return {
        wallet: len(seen_run_ids)
        for wallet, seen_run_ids in wallet_run_ids.items()
    }


def _whale_from_observation(
    *,
    observation: WhaleObservation,
    identity: PolymarketWhale,
) -> Whale:
    return Whale(
        identity=_identity(identity),
        observation=LeaderboardObservation(
            proxy_wallet=identity.proxy_wallet,
            candidate_source=observation.candidate_source,
            pnl_rank=observation.pnl_rank,
            volume_rank=observation.volume_rank,
            leaderboard_pnl=observation.leaderboard_pnl,
            leaderboard_volume=observation.leaderboard_volume,
            generated_at=observation.generated_at,
        ),
    )


def _tracked_whale_from_row(
    *,
    run_id: str,
    row: TrackedWhaleRow,
    identity: PolymarketWhale,
) -> TrackedWhale:
    return TrackedWhale(
        proxy_wallet=identity.proxy_wallet,
        run_id=run_id,
        generated_at=row.generated_at,
        filter_profile=row.filter_profile,
        consecutive_runs=row.consecutive_runs,
        candidate_source=row.candidate_source,
        pnl_rank=row.pnl_rank,
        volume_rank=row.volume_rank,
        leaderboard_pnl=row.leaderboard_pnl,
        leaderboard_volume=row.leaderboard_volume,
        identity=_identity(identity),
    )


def _identity(identity: PolymarketWhale) -> WhaleIdentity:
    identity_payload = {"proxy_wallet": identity.proxy_wallet, **dict(identity.identity)}
    return WhaleIdentity.model_validate(identity_payload)
