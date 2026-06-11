from __future__ import annotations

from datetime import UTC, datetime

from whale_tracker.core.time import ensure_utc
from whale_tracker.providers.polymarket.client import get_polymarket_data_client
from whale_tracker.tracker.markets.repository import get_latest_market_run_id
from whale_tracker.tracker.trades.discovery import DefaultTradeDiscoveryProfile
from whale_tracker.tracker.trades.domain import (
    TradeRunResult,
    Trades,
    TradeTrackingResult,
    TradeSource,
    TrackedTrades,
)
from whale_tracker.tracker.trades.repository import (
    list_tracked_trades,
    list_trade_sources,
    persist_trade_run,
    persist_trades,
)


class TradeTrackerService:
    def __init__(
        self,
        *,
        discovery_profile: DefaultTradeDiscoveryProfile | None = None,
    ) -> None:
        self.discovery_profile = discovery_profile or DefaultTradeDiscoveryProfile()

    async def run(
        self,
        *,
        market_run_id: str | None = None,
        now: datetime | None = None,
    ) -> TradeRunResult:
        generated_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(generated_at)
        actual_market_run_id = market_run_id or get_latest_market_run_id()
        if actual_market_run_id is None:
            raise ValueError("No market run found for trade tracking.")

        sources = list_trade_sources(market_run_id=actual_market_run_id)
        trades = await self._collect_trades(
            sources=sources,
            generated_at=generated_at,
        )
        persist_trade_run(
            run_id=run_id,
            market_run_id=actual_market_run_id,
            generated_at=generated_at,
            checked_source_count=trades.checked_source_count,
        )
        tracked_trades = persist_trades(
            run_id=run_id,
            trades=trades.trades,
            failed_source_count=len(trades.errors),
        )

        return TradeTrackingResult(
            run_id=run_id,
            market_run_id=actual_market_run_id,
            collected_trades=trades,
            tracked_trades=tracked_trades,
        )

    def list_tracked(self, *, run_id: str | None = None) -> TrackedTrades:
        return list_tracked_trades(run_id=run_id)

    async def _collect_trades(
        self,
        *,
        sources: list[TradeSource],
        generated_at: datetime,
    ) -> Trades:
        return await self.discovery_profile.run(
            client=get_polymarket_data_client(),
            sources=sources,
            generated_at=generated_at,
        )


def _build_run_id(generated_at: datetime) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-trades"
