from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from whale_tracker.core.db.engine import database_session
from whale_tracker.core.time import ensure_utc
from whale_tracker.tracker.whales.domain import (
    LeaderboardObservation,
    LeaderboardObservationMetrics,
    Whale,
    WhaleIdentity,
    Whales,
)
from whale_tracker.tracker.whales.models import (
    PolymarketWhale,
    WhaleObservation,
    WhaleRun,
)
from whale_tracker.tracker.whales.selection import ObservedInLastRunsProfile


def get_latest_discovery_run_id() -> str | None:
    return _latest_completed_run_id()


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


def list_tracked_whale_wallets(
    *,
    profile: ObservedInLastRunsProfile | None = None,
) -> list[str]:
    selection_profile = profile or ObservedInLastRunsProfile()

    with database_session() as session:
        return list(session.scalars(selection_profile.wallet_statement()))


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
            whales=whales.whales,
            whale_ids=whale_ids,
        )
        session.commit()


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
    whales: list[Whale],
    whale_ids: dict[str, int],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "whale_id": whale_ids[whale.proxy_wallet],
            "metrics": whale.observation.metrics.model_dump(mode="json"),
            "generated_at": ensure_utc(whale.observation.generated_at),
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


def _whale_from_observation(
    *,
    observation: WhaleObservation,
    identity: PolymarketWhale,
) -> Whale:
    return Whale(
        identity=_identity(identity),
        observation=LeaderboardObservation(
            proxy_wallet=identity.proxy_wallet,
            metrics=LeaderboardObservationMetrics.model_validate(observation.metrics),
            generated_at=observation.generated_at,
        ),
    )


def _identity(identity: PolymarketWhale) -> WhaleIdentity:
    identity_payload = {"proxy_wallet": identity.proxy_wallet, **dict(identity.identity)}
    return WhaleIdentity.model_validate(identity_payload)
