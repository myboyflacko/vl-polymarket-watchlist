import asyncio
import os
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine, database_session
from whale_tracker.settings import get_settings
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    MarketPosition,
    MarketRun,
)
from whale_tracker.tracker.trades.discovery import DefaultTradeDiscoveryProfile
from whale_tracker.tracker.trades.domain import Trade, TradeSource
from whale_tracker.tracker.trades.models import TradeFact, TradeRun, TradeRunItem
from whale_tracker.tracker.trades.repository import (
    list_trade_sources,
    persist_trade_run,
    persist_trades,
)


NOW = datetime(2026, 6, 1, tzinfo=UTC)
WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONDITION_ID = "0x" + "1" * 64
YES_TOKEN = "111"
NO_TOKEN = "222"


class FakeTradeClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def get_trades(self, params: Any) -> list[dict[str, Any]]:
        self.requests.append(params.output_params())
        if params.offset:
            return []

        return [
            {
                "id": "trade-1",
                "asset": YES_TOKEN,
                "side": "buy",
                "outcome": "Yes",
                "price": "0.42",
                "size": "10",
                "timestamp": "1780272000",
                "transactionHash": "0xabc",
            }
        ]


def test_trade_discovery_fetches_trades_for_wallet_condition() -> None:
    client = FakeTradeClient()
    profile = DefaultTradeDiscoveryProfile()
    source = TradeSource(
        proxy_wallet=WALLET_ONE,
        condition_id=CONDITION_ID,
        market_ids_by_token={YES_TOKEN: 123},
    )

    result = asyncio.run(
        profile.run(client=client, sources=[source], generated_at=NOW)
    )

    assert client.requests == [
        {
            "limit": 10000,
            "offset": 0,
            "takerOnly": True,
            "market": CONDITION_ID,
            "user": WALLET_ONE,
        }
    ]
    assert result.checked_source_count == 1
    assert result.errors == []
    trade = result.trades[0]
    assert trade.trade_key == "api:trade-1"
    assert trade.market_id == 123
    assert trade.side == "BUY"
    assert trade.price == 0.42
    assert trade.size == 10
    assert trade.value == 4.2
    assert trade.trade_timestamp == datetime(2026, 6, 1, tzinfo=UTC)


def test_trade_sources_deduplicate_wallet_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    _insert_market_run_with_positions(database_url)

    sources = list_trade_sources(market_run_id="markets-run-1")

    assert sources == [
        TradeSource(
            proxy_wallet=WALLET_ONE,
            condition_id=CONDITION_ID,
            market_ids_by_token={YES_TOKEN: 1, NO_TOKEN: 2},
        )
    ]


def test_trade_persistence_deduplicates_trade_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    _insert_market_run_with_positions(database_url)
    persist_trade_run(
        run_id="trades-run-1",
        market_run_id="markets-run-1",
        generated_at=NOW,
        checked_source_count=1,
    )
    trade = Trade(
        proxy_wallet=WALLET_ONE,
        condition_id=CONDITION_ID,
        trade_key="api:trade-1",
        market_id=1,
        token_id=YES_TOKEN,
        side="BUY",
        outcome="Yes",
        price=0.42,
        size=10,
        value=4.2,
        trade_timestamp=NOW,
        transaction_hash="0xabc",
        raw_payload={"id": "trade-1"},
        generated_at=NOW,
    )

    result = persist_trades(
        run_id="trades-run-1",
        trades=[trade, trade],
        failed_source_count=0,
    )

    assert result.trade_count == 1
    with database_session(database_url) as session:
        run = session.scalar(select(TradeRun))
        facts = list(session.scalars(select(TradeFact)))
        items = list(session.scalars(select(TradeRunItem)))

    assert run is not None
    assert run.stored_trade_count == 1
    assert run.failed_source_count == 0
    assert len(facts) == 1
    assert facts[0].trade_key == "api:trade-1"
    assert len(items) == 1


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


def _insert_market_run_with_positions(database_url: str) -> None:
    with database_session(database_url) as session:
        session.add(
            MarketRun(
                run_id="markets-run-1",
                whales_run_id=None,
                status="completed",
                generated_at=NOW,
                checked_market_count=2,
            )
        )
        yes = MarketIdentity(
            id=1,
            token_id=YES_TOKEN,
            condition_id=CONDITION_ID,
            title="Title",
            slug="slug",
            outcome="Yes",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        no = MarketIdentity(
            id=2,
            token_id=NO_TOKEN,
            condition_id=CONDITION_ID,
            title="Title",
            slug="slug",
            outcome="No",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        session.add_all([yes, no])
        session.flush()
        session.add_all(
            [
                MarketPosition(
                    run_id="markets-run-1",
                    market_id=yes.id,
                    wallet=WALLET_ONE,
                    size=10,
                    current_value=4.2,
                    avg_price=0.4,
                    cur_price=0.42,
                    negative_risk=False,
                    generated_at=NOW,
                ),
                MarketPosition(
                    run_id="markets-run-1",
                    market_id=no.id,
                    wallet=WALLET_ONE,
                    size=5,
                    current_value=2.5,
                    avg_price=0.5,
                    cur_price=0.5,
                    negative_risk=False,
                    generated_at=NOW,
                ),
            ]
        )
        session.commit()


def _set_database_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    parsed_url = make_url(database_url)
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_DB", parsed_url.database or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_USER", parsed_url.username or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PASSWORD", parsed_url.password or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_HOST", parsed_url.host or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PORT", str(parsed_url.port or 5432))
