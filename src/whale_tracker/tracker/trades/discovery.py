from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from whale_tracker.providers.polymarket.client import PolymarketDataClient
from whale_tracker.tracker.trades.domain import TradeSource, Trades
from whale_tracker.tracker.trades.helpers import collect_position_trades


class DefaultTradeDiscoveryProfile(BaseModel):
    name: str = "default_trade_discovery"

    async def run(
        self,
        *,
        client: PolymarketDataClient,
        sources: list[TradeSource],
        generated_at: datetime,
    ) -> Trades:
        if not sources:
            return Trades(generated_at=generated_at)

        trades, errors = await collect_position_trades(
            client=client,
            sources=sources,
            generated_at=generated_at,
        )
        return Trades(
            trades=trades,
            errors=errors,
            checked_source_count=len(sources),
            generated_at=generated_at,
        )
