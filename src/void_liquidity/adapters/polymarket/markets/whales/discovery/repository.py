from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from void_liquidity.adapters.polymarket.markets.whales.discovery.models import (
    TrackedWhale,
    TrackedWhaleMetricSnapshot,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.domain import (
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    Whales,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleTrackerV2Profile,
)
from void_liquidity.data.engine import database_session


def list_tracked_whale_wallets() -> list[str]:
    with database_session() as session:
        latest_run = session.scalar(_latest_completed_run_statement())
        if latest_run is None:
            return []

        return list(
            session.scalars(
                select(TrackedWhale.proxy_wallet)
                .where(TrackedWhale.run_id == latest_run.run_id)
                .order_by(TrackedWhale.id)
            )
        )


def list_latest_whales() -> Whales:
    with database_session() as session:
        latest_run = session.scalar(_latest_completed_run_statement())
        if latest_run is None:
            return Whales(
                whales=[],
                candidate_wallet_count=0,
                checked_wallet_count=0,
                generated_at=datetime.min.replace(tzinfo=UTC),
                profile_version="unknown",
            )

        snapshots = list(
            session.scalars(
                select(TrackedWhaleMetricSnapshot)
                .where(TrackedWhaleMetricSnapshot.run_id == latest_run.run_id)
                .order_by(TrackedWhaleMetricSnapshot.id)
            )
        )

        return Whales(
            whales=[_whale_from_snapshot(snapshot) for snapshot in snapshots],
            candidate_wallet_count=latest_run.candidate_wallet_count,
            checked_wallet_count=latest_run.checked_wallet_count,
            generated_at=latest_run.generated_at,
            profile_version=latest_run.profile_version,
        )


def persist_whale_tracker_v2_run(
    *,
    profile: WhaleTrackerV2Profile,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    generated_at: datetime,
    whales: Whales,
) -> None:
    with database_session() as session:
        session.add(
            WhaleTrackerRun(
                run_id=run_id,
                profile_version=profile.profile_version,
                status="completed",
                started_at=started_at,
                finished_at=finished_at,
                generated_at=generated_at,
                candidate_wallet_count=whales.candidate_wallet_count,
                checked_wallet_count=whales.checked_wallet_count,
                accepted_wallet_count=len(whales.whales),
                profile=profile.model_dump(mode="json"),
                report_path=None,
            )
        )
        session.flush()
        _upsert_tracked_whales(
            session=session,
            run_id=run_id,
            seen_at=generated_at,
            whales=whales.whales,
        )
        _insert_metric_snapshots(
            session=session,
            run_id=run_id,
            generated_at=generated_at,
            whales=whales.whales,
        )
        session.commit()


def _upsert_tracked_whales(
    *,
    session: Session,
    run_id: str,
    seen_at: datetime,
    whales: Iterable[Whale],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "proxy_wallet": whale.proxy_wallet,
            "first_seen": seen_at,
            "last_seen": seen_at,
        }
        for whale in whales
    ]

    if not rows:
        return

    statement = insert(TrackedWhale).values(rows)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[TrackedWhale.proxy_wallet],
            set_={
                "run_id": run_id,
                "last_seen": seen_at,
            },
        )
    )


def _insert_metric_snapshots(
    *,
    session: Session,
    run_id: str,
    generated_at: datetime,
    whales: Iterable[Whale],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "proxy_wallet": whale.proxy_wallet,
            "metrics": whale.metrics.model_dump(mode="json"),
            "collection_quality": whale.metrics.collection_quality.model_dump(
                mode="json"
            ),
            "generated_at": generated_at,
        }
        for whale in whales
    ]

    if rows:
        session.add_all(TrackedWhaleMetricSnapshot(**row) for row in rows)


def _latest_completed_run_statement():
    return (
        select(WhaleTrackerRun)
        .where(WhaleTrackerRun.status == "completed")
        .order_by(
            WhaleTrackerRun.generated_at.desc(),
            WhaleTrackerRun.run_id.desc(),
        )
        .limit(1)
    )


def _whale_from_snapshot(snapshot: TrackedWhaleMetricSnapshot) -> Whale:
    metrics = dict(snapshot.metrics)
    metrics.pop("ranking", None)
    return Whale(
        identity=WhaleIdentity(proxy_wallet=snapshot.proxy_wallet),
        metrics=WhaleMetrics.model_validate(metrics),
    )
