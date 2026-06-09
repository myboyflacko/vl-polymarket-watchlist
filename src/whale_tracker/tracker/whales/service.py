from __future__ import annotations

from datetime import UTC, datetime

from whale_tracker.core.time import ensure_utc
from whale_tracker.providers.polymarket.client import get_polymarket_data_client
from whale_tracker.tracker.whales.domain import (
    TrackedWhales,
    WhaleRunResult,
    WhaleTrackingResult,
    Whales,
)
from whale_tracker.tracker.whales.discovery import WhaleDiscoveryProfile
from whale_tracker.tracker.whales.helpers import (
    collect_leaderboard_whales,
    fetch_leaderboards_from_polymarket,
    select_leaderboard_candidates,
)
from whale_tracker.tracker.whales.repository import (
    list_tracked_whales,
    list_whale_observations,
    persist_tracked_whales,
    persist_whale_run,
)


class WhaleTrackerService:
    def __init__(
        self,
        discovery_profile: WhaleDiscoveryProfile | None = None,
    ) -> None:
        self.discovery_profile = discovery_profile or WhaleDiscoveryProfile()

    async def run(self, *, now: datetime | None = None) -> WhaleRunResult:
        started_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(started_at, suffix="whales")

        whales = await self.discover(now=started_at)
        persist_whale_run(
            run_id=run_id,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            whales=whales,
        )
        tracked_whales = persist_tracked_whales(run_id=run_id)

        return WhaleTrackingResult(
            run_id=run_id,
            whales=whales,
            tracked_whales=tracked_whales,
        )

    async def discover(self, *, now: datetime | None = None) -> Whales:
        generated_at = ensure_utc(now or datetime.now(UTC))
        client = get_polymarket_data_client()
        pnl_entries, volume_entries = await fetch_leaderboards_from_polymarket(
            client=client,
            profile=self.discovery_profile,
        )
        candidates = select_leaderboard_candidates(
            pnl_entries=pnl_entries,
            volume_entries=volume_entries,
            wallet_count=self.discovery_profile.wallet_count,
        )
        return collect_leaderboard_whales(
            profile=self.discovery_profile,
            candidates=candidates,
            now=generated_at,
        )

    def list_observations(self, *, run_id: str | None = None) -> Whales:
        return list_whale_observations(run_id)

    def list_tracked(self, *, run_id: str | None = None) -> TrackedWhales:
        return list_tracked_whales(run_id)


def _build_run_id(generated_at: datetime, *, suffix: str) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-{suffix}"
