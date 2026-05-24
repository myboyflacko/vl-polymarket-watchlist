from collections import Counter
from datetime import UTC, datetime
from typing import Any

from void_liquidity.adapters.polymarket.signals.signal_discovery.schemas import (
    WhaleTrackingProfile,
)
from void_liquidity.logging import VoidLogger


logger = VoidLogger(__name__)


class WhaleTrackerRunLog:
    def __init__(self, profile: WhaleTrackingProfile, run_id: str) -> None:
        self.profile = profile
        self.run_id = run_id
        self.started_at = datetime.now(UTC)

    def start(self) -> None:
        logger.log_event(
            "polymarket.track_whales.run_started",
            level="INFO",
            run_id=self.run_id,
            started_at=self.started_at.isoformat(),
            profile_version=self.profile.profile_version,
            target_wallet_count=self.profile.target_wallet_count,
            wallet_batch_size=self.profile.wallet_batch_size,
        )

    def finish(self) -> None:
        finished_at = datetime.now(UTC)
        logger.log_event(
            "polymarket.track_whales.run_finished",
            level="INFO",
            run_id=self.run_id,
            started_at=self.started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=(finished_at - self.started_at).total_seconds(),
        )

    def fail(self, exc: Exception) -> None:
        failed_at = datetime.now(UTC)
        logger.log_error(
            "polymarket.track_whales.run_failed",
            exc,
            run_id=self.run_id,
            started_at=self.started_at.isoformat(),
            failed_at=failed_at.isoformat(),
            duration_seconds=(failed_at - self.started_at).total_seconds(),
            profile_version=self.profile.profile_version,
        )

    def report(
        self,
        *,
        candidate_wallet_count: int,
        checked_wallet_count: int,
        whales: dict[str, dict[str, Any]],
        reject_summary: Counter[str],
        candidate_pool_summary: Counter[str],
    ) -> None:
        logger.log_event(
            "polymarket.track_whales.report",
            level="INFO",
            run_id=self.run_id,
            generated_at=datetime.now(UTC).isoformat(),
            candidate_wallet_count=candidate_wallet_count,
            checked_wallet_count=checked_wallet_count,
            wallet_count=len(whales),
            reject_summary=dict(sorted(reject_summary.items())),
            candidate_pool_summary=dict(sorted(candidate_pool_summary.items())),
        )
