import asyncio
from datetime import UTC, datetime

from vl_polymarket_watchlist.orderbooks import service
from vl_polymarket_watchlist.orderbooks.domain import OrderbookReadiness


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_orderbook_service_skips_before_creating_run(monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "get_orderbook_readiness",
        lambda *, now, max_age_hours: OrderbookReadiness(
            ready=False,
            reason="no_completed_discovery_run",
        ),
    )

    def fail_create_run(**kwargs):
        raise AssertionError("orderbook run should not be created")

    monkeypatch.setattr(service, "create_orderbook_collection_run", fail_create_run)

    result = asyncio.run(service.OrderbookCollectionService().run(now=NOW))

    assert result.status == "skipped"
    assert result.run_id is None
    assert result.skip_reason == "no_completed_discovery_run"
