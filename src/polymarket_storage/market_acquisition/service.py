from __future__ import annotations

from datetime import UTC, datetime

from polymarket_storage.core.time import ensure_utc
from polymarket_storage.market_acquisition.domain import (
    CollectorRunResult,
    MarketCollectorStrategy,
)
from polymarket_storage.market_acquisition.repository import persist_collector_run
from polymarket_storage.market_acquisition.strategies import (
    LeaderboardCurrentPositionsStrategy,
)
from polymarket_storage.polymarket.client import get_polymarket_data_client


class MarketCollectorService:
    def __init__(
        self,
        *,
        strategy: MarketCollectorStrategy | None = None,
    ) -> None:
        self.strategy = strategy or LeaderboardCurrentPositionsStrategy()

    async def run(self, *, now: datetime | None = None) -> CollectorRunResult:
        generated_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(generated_at)
        collected = await self.strategy.run(
            client=get_polymarket_data_client(),
            generated_at=generated_at,
        )
        stored_market_count = persist_collector_run(
            run_id=run_id,
            strategy_name=self.strategy.name,
            strategy_params=self.strategy.params(),
            generated_at=generated_at,
            checked_market_count=collected.checked_market_count,
            markets=collected.markets,
        )
        return CollectorRunResult(
            run_id=run_id,
            strategy_name=self.strategy.name,
            strategy_params=self.strategy.params(),
            markets=collected.markets,
            errors=collected.errors,
            checked_market_count=collected.checked_market_count,
            stored_market_count=stored_market_count,
            generated_at=generated_at,
        )


def _build_run_id(generated_at: datetime) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-markets"
