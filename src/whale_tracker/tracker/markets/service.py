from __future__ import annotations

from datetime import UTC, datetime

from whale_tracker.core.time import ensure_utc
from whale_tracker.providers.polymarket.client import get_polymarket_data_client
from whale_tracker.tracker.markets.domain import (
    MarketRunResult,
    MarketTrackingResult,
    Markets,
    TrackedMarkets,
)
from whale_tracker.tracker.markets.discovery import DefaultMarketDiscoveryProfile
from whale_tracker.tracker.markets.filter import (
    TrackedMarketFilterProfile,
    build_market_candidates,
)
from whale_tracker.tracker.markets.repository import (
    list_tracked_markets,
    persist_market_run,
    persist_tracked_markets,
)
from whale_tracker.tracker.whales.repository import get_latest_discovery_run_id


class MarketTrackerService:
    def __init__(
        self,
        *,
        discovery_profile: DefaultMarketDiscoveryProfile | None = None,
        filter_profile: TrackedMarketFilterProfile | None = None,
    ) -> None:
        self.discovery_profile = discovery_profile or DefaultMarketDiscoveryProfile()
        self.filter_profile = filter_profile or TrackedMarketFilterProfile()

    def register_filter(self, profile: TrackedMarketFilterProfile) -> None:
        self.filter_profile = profile

    async def run(
        self,
        *,
        whales_run_id: str | None = None,
        now: datetime | None = None,
    ) -> MarketRunResult:
        generated_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(generated_at)
        actual_whales_run_id = whales_run_id or get_latest_discovery_run_id()

        markets = await self._collect_markets(
            whales_run_id=actual_whales_run_id,
            generated_at=generated_at,
        )
        candidates = build_market_candidates(markets.positions)
        tracked_candidates = self.filter_profile.run(candidates)
        persist_market_run(
            run_id=run_id,
            whales_run_id=actual_whales_run_id,
            generated_at=generated_at,
            checked_market_count=len(candidates),
        )
        tracked_markets = persist_tracked_markets(
            run_id=run_id,
            whales_run_id=actual_whales_run_id,
            generated_at=generated_at,
            markets=tracked_candidates,
            filter_profile=self.filter_profile.name,
        )

        return MarketTrackingResult(
            run_id=run_id,
            whales_run_id=actual_whales_run_id,
            collected_markets=markets,
            tracked_markets=tracked_markets,
        )

    def list_tracked(self, *, run_id: str | None = None) -> TrackedMarkets:
        return list_tracked_markets(run_id=run_id)

    async def _collect_markets(
        self,
        *,
        whales_run_id: str | None,
        generated_at: datetime,
    ) -> Markets:
        return await self.discovery_profile.run(
            client=get_polymarket_data_client(),
            whales_run_id=whales_run_id,
            generated_at=generated_at,
        )


def _build_run_id(generated_at: datetime) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-markets"
