from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from void_liquidity.adapters.polymarket.discovery.whales.metrics import (
    _build_payload,
)
from void_liquidity.adapters.polymarket.discovery.whales.models import (
    TrackedWhale,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.discovery.whales.schemas import (
    WhaleTrackingProfile,
)
from void_liquidity.data import database_session


def persist_whale_tracker_run(
    *,
    profile: WhaleTrackingProfile,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    generated_at: datetime,
    candidate_wallet_count: int,
    checked_wallet_count: int,
    whales: dict[str, dict[str, Any]],
    report_path: Path,
) -> None:
    public_whales = _build_payload(whales=whales, run_id=run_id)["whales"]

    with database_session() as session:
        session.add(
            WhaleTrackerRun(
                run_id=run_id,
                profile_version=profile.profile_version,
                status="completed",
                started_at=started_at,
                finished_at=finished_at,
                generated_at=generated_at,
                candidate_wallet_count=candidate_wallet_count,
                checked_wallet_count=checked_wallet_count,
                accepted_wallet_count=len(public_whales),
                profile=profile.model_dump(mode="json"),
                report_path=str(report_path),
            )
        )
        session.flush()
        _upsert_tracked_whales(
            session=session,
            run_id=run_id,
            seen_at=generated_at,
            whales=public_whales.values(),
        )
        session.commit()


def _upsert_tracked_whales(
    *,
    session: Session,
    run_id: str,
    seen_at: datetime,
    whales: Iterable[dict[str, Any]],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "proxy_wallet": whale["metadata"]["proxy_wallet"],
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
