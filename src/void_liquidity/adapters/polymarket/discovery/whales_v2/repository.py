from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from void_liquidity.adapters.polymarket.discovery.whales.models import (
    TrackedWhale,
    TrackedWhaleMetricSnapshot,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.discovery.whales_v2.domain import Whale, Whales
from void_liquidity.adapters.polymarket.discovery.whales_v2.profiles import (
    WhaleTrackerV2Profile,
)
from void_liquidity.data import database_session


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
                accepted_wallet_count=whales.wallet_count,
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
