from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from whale_tracker.core.db.engine import database_session
from whale_tracker.tracker.whales.domain import (
    FilteredWhales,
    ScoredWhale,
    ScoredWhales,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    Whales,
)
from whale_tracker.tracker.whales.models import PolymarketWhale, WhaleMetric, WhaleRun


def get_latest_discovery_run_id() -> str | None:
    return _latest_completed_run_id()


def get_latest_selection_run_id() -> str | None:
    return _latest_completed_run_id()


def list_discovered_whale_wallets(run_id: str) -> list[str]:
    return list_selected_whale_wallets(run_id)


def list_latest_discovered_whale_wallets() -> list[str]:
    return list_latest_selected_whale_wallets()


def list_discovered_whales(run_id: str) -> Whales:
    return list_selected_whales(run_id)


def list_latest_discovered_whales() -> Whales:
    latest_run_id = get_latest_discovery_run_id()
    if latest_run_id is None:
        return _empty_whales()

    return list_discovered_whales(latest_run_id)


def list_selected_whale_wallets(run_id: str) -> list[str]:
    with database_session() as session:
        return list(
            session.scalars(
                select(PolymarketWhale.proxy_wallet)
                .join(WhaleMetric, WhaleMetric.whale_id == PolymarketWhale.id)
                .where(WhaleMetric.run_id == run_id)
                .order_by(WhaleMetric.id)
            )
        )


def list_latest_selected_whale_wallets() -> list[str]:
    latest_run_id = get_latest_selection_run_id()
    if latest_run_id is None:
        return []

    return list_selected_whale_wallets(latest_run_id)


def list_selected_whales(run_id: str) -> Whales:
    with database_session() as session:
        run = session.get(WhaleRun, run_id)
        if run is None:
            return _empty_whales()

        rows = list(
            session.execute(
                select(WhaleMetric, PolymarketWhale)
                .join(PolymarketWhale, WhaleMetric.whale_id == PolymarketWhale.id)
                .where(WhaleMetric.run_id == run_id)
                .order_by(WhaleMetric.id)
            )
        )

        return Whales(
            whales=[
                _whale_from_metric(metric=metric, identity=identity)
                for metric, identity in rows
            ],
            candidate_wallet_count=run.checked_wallet_count,
            checked_wallet_count=run.checked_wallet_count,
            generated_at=run.generated_at,
            profile_version=run.profile_version,
        )


def persist_whale_run(
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    whales: Whales,
    filtered_whales: FilteredWhales,
    scored_whales: ScoredWhales | None,
) -> None:
    metric_entries = _metric_entries(
        filtered_whales=filtered_whales,
        scored_whales=scored_whales,
    )
    scored_wallet_count = len(metric_entries)
    removed_wallet_count = (
        filtered_whales.removed_wallet_count
        + (scored_whales.removed_wallet_count if scored_whales is not None else 0)
    )

    with database_session() as session:
        session.add(
            WhaleRun(
                run_id=run_id,
                status="completed",
                profile_version=whales.profile_version,
                started_at=started_at,
                finished_at=finished_at,
                generated_at=whales.generated_at,
                filter_profile=filtered_whales.profile_name,
                scoring_profile=(
                    scored_whales.profile_name if scored_whales is not None else ""
                ),
                checked_wallet_count=whales.checked_wallet_count,
                filtered_wallet_count=filtered_whales.wallet_count,
                scored_wallet_count=scored_wallet_count,
                removed_wallet_count=removed_wallet_count,
            )
        )
        session.flush()
        whale_ids = _upsert_whales(
            session=session,
            seen_at=whales.generated_at,
            whales=[entry.whale for entry in metric_entries],
        )
        _upsert_whale_metrics(
            session=session,
            run_id=run_id,
            generated_at=whales.generated_at,
            metric_entries=metric_entries,
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


def _metric_entries(
    *,
    filtered_whales: FilteredWhales,
    scored_whales: ScoredWhales | None,
) -> list[ScoredWhale]:
    if scored_whales is not None:
        return scored_whales.whales

    return [
        ScoredWhale(whale=whale, score=0.0)
        for whale in filtered_whales.whales
    ]


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


def _upsert_whale_metrics(
    *,
    session: Session,
    run_id: str,
    generated_at: datetime,
    metric_entries: list[ScoredWhale],
    whale_ids: dict[str, int],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "whale_id": whale_ids[entry.whale.proxy_wallet],
            "score": entry.score,
            "metrics": entry.whale.metrics.model_dump(mode="json"),
            "generated_at": generated_at,
        }
        for entry in metric_entries
        if entry.whale.proxy_wallet in whale_ids
    ]
    if not rows:
        return

    statement = insert(WhaleMetric).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "whale_id"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[WhaleMetric.run_id, WhaleMetric.whale_id],
            set_=update_columns,
        )
    )


def _whale_from_metric(*, metric: WhaleMetric, identity: PolymarketWhale) -> Whale:
    identity_payload = {"proxy_wallet": identity.proxy_wallet, **dict(identity.identity)}
    return Whale(
        identity=WhaleIdentity.model_validate(identity_payload),
        metrics=WhaleMetrics.model_validate(dict(metric.metrics)),
    )
