import asyncio

import pytest

from void_liquidity.adapters.polymarket.markets.whales.domain import (
    MarketCandidate,
    WhaleMarketCandidates,
    WhalePosition,
    WhalePositionCollectionError,
)
from void_liquidity.adapters.polymarket.markets.whales.collector import (
    DEFAULT_MIN_WHALE_COUNT,
)
from void_liquidity.adapters.polymarket.markets.whales.events import (
    POLYMARKET_WHALE_MARKETS_COMPLETED,
    POLYMARKET_WHALE_MARKETS_DISCOVERED,
    POLYMARKET_WHALE_MARKETS_FAILED,
    POLYMARKET_WHALE_MARKETS_PERSIST_COMPLETED,
    POLYMARKET_WHALE_MARKETS_PERSIST_FAILED,
    POLYMARKET_WHALE_MARKETS_PERSIST_STARTED,
    POLYMARKET_WHALE_MARKETS_REQUESTED,
    POLYMARKET_WHALE_MARKETS_STARTED,
)
from void_liquidity.bindings.polymarket.markets import whales as binding_module
from void_liquidity.bindings.polymarket.markets.whales import (
    PolymarketWhaleMarketsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus


def _request() -> DomainEvent:
    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_MARKETS_REQUESTED,
        source="workflow.whale_market_candidates",
        correlation_id="correlation-markets",
        metadata={"workflow": "whale_market_candidates"},
    )


def _result() -> WhaleMarketCandidates:
    return WhaleMarketCandidates(
        candidates=[
            MarketCandidate(
                token_id="token-1",
                condition_id="0x" + "1" * 64,
                title="Will this happen?",
                slug="will-this-happen",
                outcome="Yes",
                whale_count=2,
                wallets=[
                    "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ],
                total_size=15,
                total_current_value=150,
                weighted_avg_price=0.4,
                cur_price=0.5,
            )
            for _ in range(12)
        ],
        positions=[
            WhalePosition(
                proxy_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                token_id="token-1",
                condition_id="0x" + "1" * 64,
                outcome="Yes",
            )
        ],
        errors=[
            WhalePositionCollectionError(
                proxy_wallet="0xcccccccccccccccccccccccccccccccccccccccc",
                message="boom",
            )
        ],
    )


def test_polymarket_whale_markets_binding_declares_runtime_contract() -> None:
    binding = PolymarketWhaleMarketsBinding()

    assert binding.spec.name == "polymarket.markets.whales"
    assert binding.spec.consumes == (POLYMARKET_WHALE_MARKETS_REQUESTED,)
    assert POLYMARKET_WHALE_MARKETS_COMPLETED in binding.spec.produces
    assert POLYMARKET_WHALE_MARKETS_DISCOVERED in binding.spec.produces
    assert POLYMARKET_WHALE_MARKETS_PERSIST_COMPLETED in binding.spec.produces


def test_polymarket_whale_markets_binding_collects_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[dict] = []

    async def fake_collect_whale_market_candidates(
        *,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> WhaleMarketCandidates:
        assert min_whale_count == DEFAULT_MIN_WHALE_COUNT
        return _result()

    monkeypatch.setattr(
        binding_module,
        "collect_whale_market_candidates",
        fake_collect_whale_market_candidates,
    )

    def fake_persist_market_candidates(candidates, **kwargs) -> None:
        persisted.append({"candidates": candidates, **kwargs})

    monkeypatch.setattr(
        binding_module,
        "persist_market_candidates",
        fake_persist_market_candidates,
    )
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    result = asyncio.run(PolymarketWhaleMarketsBinding().handle(event=_request(), bus=bus))

    assert result == _result()
    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_MARKETS_STARTED,
        POLYMARKET_WHALE_MARKETS_DISCOVERED,
        POLYMARKET_WHALE_MARKETS_PERSIST_STARTED,
        POLYMARKET_WHALE_MARKETS_PERSIST_COMPLETED,
        POLYMARKET_WHALE_MARKETS_COMPLETED,
    ]
    assert persisted
    assert persisted[0]["run_id"] == emitted_events[0].payload["run_id"]
    assert persisted[0]["min_whale_count"] == DEFAULT_MIN_WHALE_COUNT
    assert persisted[0]["position_count"] == 1
    assert persisted[0]["error_count"] == 1
    assert {event.source for event in emitted_events} == {
        "binding.polymarket.markets.whales"
    }
    assert {event.correlation_id for event in emitted_events} == {
        "correlation-markets"
    }
    discovered = emitted_events[1].payload
    assert discovered["candidate_count"] == 12
    assert discovered["position_count"] == 1
    assert discovered["error_count"] == 1
    assert discovered["min_whale_count"] == DEFAULT_MIN_WHALE_COUNT
    assert "candidate_preview" not in discovered
    assert "candidates" not in discovered
    assert discovered["error_summary"] == [{"message": "boom", "count": 1}]
    assert emitted_events[-1].payload["partial"] is True


def test_polymarket_whale_markets_binding_publishes_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_collect_whale_market_candidates(
        *,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> WhaleMarketCandidates:
        raise RuntimeError("collector failed")

    monkeypatch.setattr(
        binding_module,
        "collect_whale_market_candidates",
        fail_collect_whale_market_candidates,
    )
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="collector failed"):
        asyncio.run(PolymarketWhaleMarketsBinding().handle(event=_request(), bus=bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_MARKETS_STARTED,
        POLYMARKET_WHALE_MARKETS_FAILED,
    ]
    assert emitted_events[-1].payload["error_type"] == "RuntimeError"
    assert emitted_events[-1].payload["error"] == "collector failed"


def test_polymarket_whale_markets_binding_publishes_persist_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_collect_whale_market_candidates(
        *,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> WhaleMarketCandidates:
        return _result()

    def fail_persist_market_candidates(candidates, **kwargs) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(
        binding_module,
        "collect_whale_market_candidates",
        fake_collect_whale_market_candidates,
    )
    monkeypatch.setattr(
        binding_module,
        "persist_market_candidates",
        fail_persist_market_candidates,
    )
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="db down"):
        asyncio.run(PolymarketWhaleMarketsBinding().handle(event=_request(), bus=bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_MARKETS_STARTED,
        POLYMARKET_WHALE_MARKETS_DISCOVERED,
        POLYMARKET_WHALE_MARKETS_PERSIST_STARTED,
        POLYMARKET_WHALE_MARKETS_PERSIST_FAILED,
        POLYMARKET_WHALE_MARKETS_FAILED,
    ]
    assert emitted_events[-2].payload["error_type"] == "RuntimeError"
    assert emitted_events[-2].payload["error"] == "db down"
