import asyncio
from datetime import date

import pytest

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import (
    MarketCandidate,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    QualifiedMarket,
    QualifiedMarketResult,
    WhaleQualifiedMarketProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.events import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED as POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_COMPLETED,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.events import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED as POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_FAILED,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.events import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED as POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
)
from void_liquidity.bindings.polymarket.markets.whales import qualified as binding_module
from void_liquidity.bindings.polymarket.markets.whales.qualified import (
    PolymarketWhaleQualifiedMarketsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.pipeline.markets.qualified import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
)


def _request() -> DomainEvent:
    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,
        source="workflow.whale_market_procurement",
        correlation_id="correlation-qualified",
        metadata={"workflow": "whale_market_procurement"},
        payload={"profile": {"name": "high_value"}, "limit": 1},
    )


def _result() -> QualifiedMarketResult:
    profile = WhaleQualifiedMarketProfile(name="high_value")
    return QualifiedMarketResult(
        profile=profile,
        qualified_markets=[
            QualifiedMarket(
                profile=profile.name,
                candidate=_candidate(token_id="token-1"),
                score=100,
                price_delta=0.1,
                price_delta_pct=0.25,
                value_per_wallet=50,
            )
        ],
    )


def test_polymarket_whale_qualified_binding_declares_runtime_contract() -> None:
    binding = PolymarketWhaleQualifiedMarketsBinding()

    assert binding.spec.name == "polymarket.markets.whales.qualified"
    assert binding.spec.consumes == (POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,)
    assert binding.spec.produces == (
        POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_COMPLETED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_FAILED,
    )


def test_polymarket_whale_qualified_binding_derives_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeQualifiedMarketService:
        def __init__(self, profile: WhaleQualifiedMarketProfile) -> None:
            assert profile.name == "high_value"

        def list(self, *, limit: int | None = None) -> QualifiedMarketResult:
            assert limit == 1
            return _result()

    monkeypatch.setattr(
        binding_module,
        "WhaleQualifiedMarketService",
        FakeQualifiedMarketService,
    )
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    result = asyncio.run(
        PolymarketWhaleQualifiedMarketsBinding().handle(_request(), bus)
    )

    assert result == _result()
    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_COMPLETED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED,
    ]
    assert {event.source for event in emitted_events} == {
        "binding.polymarket.markets.whales.qualified"
    }
    assert emitted_events[2].payload["qualified_market_count"] == 1
    assert emitted_events[2].payload["token_ids"] == ["token-1"]


def test_polymarket_whale_qualified_binding_publishes_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingQualifiedMarketService:
        def __init__(self, profile: WhaleQualifiedMarketProfile) -> None:
            self.profile = profile

        def list(self, *, limit: int | None = None) -> QualifiedMarketResult:
            raise RuntimeError("qualification failed")

    monkeypatch.setattr(
        binding_module,
        "WhaleQualifiedMarketService",
        FailingQualifiedMarketService,
    )
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="qualification failed"):
        asyncio.run(PolymarketWhaleQualifiedMarketsBinding().handle(_request(), bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_FAILED,
        POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED,
    ]
    assert emitted_events[-1].payload["error_type"] == "RuntimeError"


def _candidate(*, token_id: str) -> MarketCandidate:
    return MarketCandidate(
        token_id=token_id,
        condition_id="0x" + "1" * 64,
        title="Will this happen?",
        slug="will-this-happen",
        outcome="Yes",
        whale_count=2,
        wallets=["wallet-1", "wallet-2"],
        total_size=10,
        total_current_value=100,
        weighted_avg_price=0.4,
        cur_price=0.5,
        opposite_token_id="no-token",
        opposite_outcome="No",
        end_date=date(2026, 7, 20),
    )
