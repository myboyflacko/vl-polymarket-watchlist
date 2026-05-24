from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from void_liquidity.adapters.polymarket.sources.track_whales.metrics import (
    _build_payload,
)
from void_liquidity.adapters.polymarket.sources.track_whales.models import (
    TrackedWhale,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.sources.track_whales.schemas import (
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
        session.add_all(
            _tracked_whale_row(run_id=run_id, whale=whale)
            for whale in public_whales.values()
        )
        session.commit()


def _tracked_whale_row(run_id: str, whale: dict[str, Any]) -> TrackedWhale:
    metadata = whale["metadata"]
    metrics = whale["metrics"]
    leaderboard = metrics["leaderboard"]
    exposure = metrics["exposure"]
    closed_positions = metrics["closed_positions"]
    activity = metrics["activity"]

    return TrackedWhale(
        run_id=run_id,
        proxy_wallet=metadata["proxy_wallet"],
        user_name=metadata["user_name"],
        x_username=metadata["x_username"],
        verified_badge=metadata["verified_badge"],
        candidate_pool_source=leaderboard["candidate_pool_source"],
        current_position_value=exposure["current_position_value"],
        closed_positions_pnl=closed_positions["closed_positions_pnl"],
        roi=closed_positions["roi"],
        profit_factor=closed_positions["profit_factor"],
        activity_volume_window=activity["activity_volume_window"],
        last_activity_at=activity["last_activity_at"],
        leaderboard=leaderboard,
        exposure=exposure,
        closed_positions=closed_positions,
        activity=activity,
    )
