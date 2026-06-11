import asyncio
import os
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine, database_session
from whale_tracker.providers.polymarket.params.orderbook import (
    OrderBookRequest,
    OrderBooksParams,
)
from whale_tracker.settings import get_settings
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    MarketObservation,
    MarketRun,
)
from whale_tracker.tracker.orderbooks import service as service_module
from whale_tracker.tracker.orderbooks.discovery import OrderBookDiscoveryProfile
from whale_tracker.tracker.orderbooks.domain import TrackedMarketOrderBookSource
from whale_tracker.tracker.orderbooks.models import OrderBookMetric, OrderBookRun
from whale_tracker.tracker.orderbooks.service import OrderBookTrackerService


NOW = datetime(2026, 6, 1, tzinfo=UTC)
CONDITION_ID = "0x" + "1" * 64
YES_TOKEN = "111"
NO_TOKEN = "222"


class FakeOrderBookClient:
    def __init__(self) -> None:
        self.requests: list[list[dict[str, str]]] = []

    async def get_order_books(self, params: Any) -> list[dict[str, Any]]:
        body = params.output_body()
        self.requests.append(body)
        return [_orderbook_response(token_id=item["token_id"]) for item in body]


def test_orderbook_params_serializes_request_body() -> None:
    params = OrderBooksParams(
        root=[
            OrderBookRequest(token_id=YES_TOKEN),
            OrderBookRequest(token_id=NO_TOKEN, side="BUY"),
        ]
    )

    assert params.output_body() == [
        {"token_id": YES_TOKEN},
        {"token_id": NO_TOKEN, "side": "BUY"},
    ]


def test_orderbook_discovery_limits_depth_and_computes_metrics() -> None:
    client = FakeOrderBookClient()
    profile = OrderBookDiscoveryProfile(depth=5)

    result = asyncio.run(
        profile.run(
            client=client,
            sources=[
                TrackedMarketOrderBookSource(
                    market_id=123,
                    token_id=YES_TOKEN,
                    condition_id=CONDITION_ID,
                    title="Title",
                    slug="slug",
                    outcome="Yes",
                )
            ],
            generated_at=NOW,
        )
    )

    assert client.requests == [[{"token_id": YES_TOKEN}]]
    assert result.checked_market_count == 1
    assert result.errors == []
    snapshot = result.snapshots[0]
    assert snapshot.market_id == 123
    assert len(snapshot.bids) == 5
    assert len(snapshot.asks) == 5
    assert snapshot.best_bid == 0.45
    assert snapshot.best_ask == 0.46
    assert snapshot.spread == pytest.approx(0.01)
    assert snapshot.midpoint == pytest.approx(0.455)
    assert snapshot.exchange_timestamp == datetime(2026, 6, 1, tzinfo=UTC)


def test_orderbook_tracker_run_persists_metrics_for_tracked_markets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    market_id = _insert_market_observation_run(database_url)
    client = FakeOrderBookClient()
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: client,
    )
    service = OrderBookTrackerService()

    result = asyncio.run(service.run(market_run_id="markets-run-1", now=NOW))

    assert result.run_id.endswith("-orderbooks")
    assert result.tracked_orderbooks.orderbook_count == 1
    assert client.requests == [[{"token_id": YES_TOKEN}]]

    with database_session(database_url) as session:
        run = session.scalar(select(OrderBookRun))
        metric = session.scalar(select(OrderBookMetric))

    assert run is not None
    assert run.market_run_id == "markets-run-1"
    assert run.checked_market_count == 1
    assert run.stored_orderbook_count == 1
    assert run.failed_orderbook_count == 0
    assert metric is not None
    assert metric.market_id == market_id
    assert len(metric.bids) == 5
    assert len(metric.asks) == 5


def _prepare_database(monkeypatch: pytest.MonkeyPatch) -> str:
    database_url = os.environ.get("WHALE_TRACKER_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("WHALE_TRACKER_TEST_DATABASE_URL is required for DB integration tests.")

    parsed_url = make_url(database_url)
    if "test" not in (parsed_url.database or ""):
        pytest.fail("WHALE_TRACKER_TEST_DATABASE_URL database name must contain 'test'.")

    get_settings.cache_clear()
    _set_database_env(monkeypatch, database_url)
    engine = create_database_engine(database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return database_url


def _insert_market_observation_run(database_url: str) -> int:
    with database_session(database_url) as session:
        session.add(
            MarketRun(
                run_id="markets-run-1",
                whales_run_id=None,
                status="completed",
                generated_at=NOW,
                checked_market_count=5,
            )
        )
        market = MarketIdentity(
            token_id=YES_TOKEN,
            condition_id=CONDITION_ID,
            title="Title",
            slug="slug",
            outcome="Yes",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        session.add(market)
        session.flush()
        market_id = market.id
        session.add_all(
            [
                MarketObservation(
                    run_id="markets-run-1",
                    market_id=market_id,
                    wallet=f"0x{index}",
                    size=10,
                    current_value=100,
                    avg_price=0.5,
                    cur_price=0.5,
                    negative_risk=False,
                    generated_at=NOW,
                )
                for index in range(1, 6)
            ]
        )
        session.flush()
        session.commit()

    return market_id


def _set_database_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    parsed_url = make_url(database_url)
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_DB", parsed_url.database or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_USER", parsed_url.username or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PASSWORD", parsed_url.password or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_HOST", parsed_url.host or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PORT", str(parsed_url.port or 5432))


def _orderbook_response(*, token_id: str) -> dict[str, Any]:
    return {
        "market": CONDITION_ID,
        "asset_id": token_id,
        "timestamp": "1780272000",
        "hash": f"hash-{token_id}",
        "bids": [
            {"price": str(0.45 - index * 0.01), "size": str(100 + index)}
            for index in range(6)
        ],
        "asks": [
            {"price": str(0.46 + index * 0.01), "size": str(150 + index)}
            for index in range(6)
        ],
        "min_order_size": "1",
        "tick_size": "0.01",
        "neg_risk": False,
        "last_trade_price": "0.45",
    }
