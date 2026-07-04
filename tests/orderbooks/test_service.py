import asyncio
import logging
from datetime import UTC, datetime

from vl_polymarket_watchlist.orderbooks import service
from vl_polymarket_watchlist.orderbooks.domain import (
    OrderBookCollectionItemPayload,
    OrderbookReadiness,
)


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_orderbook_service_skips_before_creating_run(monkeypatch, caplog) -> None:
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

    with caplog.at_level(logging.INFO):
        result = asyncio.run(service.OrderbookCollectionService().run(now=NOW))

    assert result.status == "skipped"
    assert result.run_id is None
    assert result.skip_reason == "no_completed_discovery_run"
    assert caplog.records[0].event == "service.skipped"
    assert caplog.records[0].context == {
        "service": "orderbooks",
        "reason": "no_completed_discovery_run",
    }


def test_orderbook_service_logs_batch_load_failure(monkeypatch, caplog) -> None:
    class FailingClient:
        async def get_order_books(self, params):
            raise RuntimeError("clob unavailable")

    _stub_ready_collection(monkeypatch, [_item("token-1")])
    monkeypatch.setattr(
        service,
        "get_polymarket_data_client",
        lambda: FailingClient(),
    )

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(service.OrderbookCollectionService().run(now=NOW))

    assert result.status == "failed"
    assert result.failure_count == 1
    assert caplog.records[0].event == "orderbook.load_failed"
    assert caplog.records[0].context == {
        "run_id": "20260601T000000000000Z-orderbooks",
        "token_ids": ["token-1"],
        "reason": "batch_request_failed",
        "error": "clob unavailable",
    }


def test_orderbook_service_logs_missing_payload(monkeypatch, caplog) -> None:
    class EmptyClient:
        async def get_order_books(self, params):
            return []

    _stub_ready_collection(monkeypatch, [_item("token-1")])
    monkeypatch.setattr(
        service,
        "get_polymarket_data_client",
        lambda: EmptyClient(),
    )

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(service.OrderbookCollectionService().run(now=NOW))

    assert result.status == "failed"
    assert result.failure_count == 1
    assert caplog.records[0].event == "orderbook.load_failed"
    assert caplog.records[0].context == {
        "run_id": "20260601T000000000000Z-orderbooks",
        "token_id": "token-1",
        "reason": "missing_payload",
    }


def _stub_ready_collection(monkeypatch, items):
    monkeypatch.setattr(
        service,
        "get_orderbook_readiness",
        lambda *, now, max_age_hours: OrderbookReadiness(ready=True),
    )
    monkeypatch.setattr(service, "create_orderbook_collection_run", lambda **kwargs: None)
    monkeypatch.setattr(
        service,
        "snapshot_collectable_watchlist",
        lambda *, run_id, selected_at: items,
    )
    monkeypatch.setattr(
        service,
        "persist_orderbook_snapshots",
        lambda *, run_id, snapshots: None,
    )
    monkeypatch.setattr(
        service,
        "complete_orderbook_collection_run",
        lambda **kwargs: None,
    )


def _item(token_id: str) -> OrderBookCollectionItemPayload:
    return OrderBookCollectionItemPayload(
        condition_id="condition-1",
        token_id=token_id,
        selected_at=NOW,
    )
