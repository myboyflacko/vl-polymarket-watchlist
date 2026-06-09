from __future__ import annotations

from datetime import UTC, datetime

from whale_tracker.core.time import ensure_utc
from whale_tracker.providers.polymarket.client import get_polymarket_data_client
from whale_tracker.tracker.markets.repository import get_latest_market_run_id
from whale_tracker.tracker.orderbooks.discovery import OrderBookDiscoveryProfile
from whale_tracker.tracker.orderbooks.domain import (
    OrderBookRunResult,
    OrderBookTrackingResult,
    TrackedOrderBooks,
)
from whale_tracker.tracker.orderbooks.repository import (
    list_tracked_market_sources,
    list_tracked_orderbooks,
    persist_orderbook_metrics,
    persist_orderbook_run,
)


class OrderBookTrackerService:
    def __init__(
        self,
        *,
        discovery_profile: OrderBookDiscoveryProfile | None = None,
    ) -> None:
        self.discovery_profile = discovery_profile or OrderBookDiscoveryProfile()

    async def run(
        self,
        *,
        market_run_id: str | None = None,
        depth: int | None = None,
        now: datetime | None = None,
    ) -> OrderBookRunResult:
        generated_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(generated_at)
        actual_market_run_id = market_run_id or get_latest_market_run_id()
        if actual_market_run_id is None:
            raise ValueError("No market run found for orderbook tracking.")

        discovery_profile = (
            self.discovery_profile
            if depth is None or depth == self.discovery_profile.depth
            else OrderBookDiscoveryProfile(
                depth=depth,
                batch_size=self.discovery_profile.batch_size,
            )
        )
        sources = list_tracked_market_sources(market_run_id=actual_market_run_id)
        orderbooks = await discovery_profile.run(
            client=get_polymarket_data_client(),
            sources=sources,
            generated_at=generated_at,
        )
        persist_orderbook_run(
            run_id=run_id,
            market_run_id=actual_market_run_id,
            generated_at=generated_at,
            depth=orderbooks.depth,
            checked_market_count=orderbooks.checked_market_count,
        )
        tracked_orderbooks = persist_orderbook_metrics(
            run_id=run_id,
            snapshots=orderbooks.snapshots,
            failed_orderbook_count=len(orderbooks.errors),
        )

        return OrderBookTrackingResult(
            run_id=run_id,
            market_run_id=actual_market_run_id,
            collected_orderbooks=orderbooks,
            tracked_orderbooks=tracked_orderbooks,
        )

    def list_tracked(self, *, run_id: str | None = None) -> TrackedOrderBooks:
        return list_tracked_orderbooks(run_id=run_id)


def _build_run_id(generated_at: datetime) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-orderbooks"
