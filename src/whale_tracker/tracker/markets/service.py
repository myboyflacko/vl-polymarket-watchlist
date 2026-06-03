from __future__ import annotations

import logging
from datetime import UTC, datetime

from whale_tracker.providers.polymarket.client import get_polymarket_data_client
from whale_tracker.tracker.markets.domain import (
    Market,
    MarketRunResult,
    MarketTrackingResult,
    Markets,
)
from whale_tracker.tracker.markets.discovery import DefaultMarketDiscoveryProfile
from whale_tracker.tracker.markets.filter import DefaultMarketFilterProfile
from whale_tracker.tracker.markets.repository import (
    list_markets,
    list_qualified_markets,
    persist_market_run,
)
from whale_tracker.tracker.markets.scoring import (
    MarketScoringProfile,
    ZScoreMarketScoringProfile,
)
from whale_tracker.tracker.whales.repository import (
    get_latest_selection_run_id,
)


logger = logging.getLogger(__name__)


class MarketTrackerService:
    def __init__(
        self,
        *,
        discovery_profile: DefaultMarketDiscoveryProfile | None = None,
        filter_profile: DefaultMarketFilterProfile | None = None,
        scoring_profile: MarketScoringProfile | None = None,
    ) -> None:
        self.discovery_profile = discovery_profile or DefaultMarketDiscoveryProfile()
        self.filter_profile = filter_profile or DefaultMarketFilterProfile()
        self.scoring_profile = scoring_profile or ZScoreMarketScoringProfile()

    def register_filter(self, profile: DefaultMarketFilterProfile) -> None:
        self.filter_profile = profile

    def register_scoring(
        self,
        profile: MarketScoringProfile | None,
    ) -> None:
        self.scoring_profile = profile

    async def run(
        self,
        *,
        whales_run_id: str | None = None,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> MarketRunResult:
        generated_at = now or datetime.now(UTC)
        run_id = _build_run_id(generated_at)
        actual_whales_run_id = whales_run_id or get_latest_selection_run_id()

        try:
            markets = await self._collect_markets(
                whales_run_id=actual_whales_run_id,
                generated_at=generated_at,
            )
            filtered_markets = self.filter_profile.run(markets)
            scored_markets = (
                self.scoring_profile.run(filtered_markets, limit=limit)
                if self.scoring_profile is not None
                else None
            )
            persist_market_run(
                run_id=run_id,
                whales_run_id=actual_whales_run_id,
                generated_at=generated_at,
                filtered_markets=filtered_markets,
                scored_markets=scored_markets,
                limit=limit,
            )
        except Exception:
            logger.exception("Market tracking run failed", extra={"run_id": run_id})
            raise

        return MarketTrackingResult(
            run_id=run_id,
            whales_run_id=actual_whales_run_id,
            collected_markets=markets,
            filtered_markets=filtered_markets,
            scored_markets=scored_markets,
            limit=limit,
        )

    def list_markets(
        self,
        *,
        run_id: str | None = None,
        limit: int | None = None,
    ) -> list[Market]:
        return list_markets(run_id=run_id, limit=limit)

    def list_qualified_markets(
        self,
        *,
        run_id: str | None = None,
        limit: int | None = None,
    ) -> list[Market]:
        return list_qualified_markets(run_id=run_id, limit=limit)

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
