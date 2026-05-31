import asyncio
from datetime import date

import pytest

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import (
    MarketCandidate,
)
from void_liquidity.adapters.polymarket.signals.whales.domain import (
    MarketSignal,
    MarketSignalResult,
    WhaleSignalProfile,
)
from void_liquidity.adapters.polymarket.signals.whales.events import (
    POLYMARKET_WHALE_SIGNALS_COMPLETED as POLYMARKET_WHALE_SIGNALS_DERIVATION_COMPLETED,
)
from void_liquidity.adapters.polymarket.signals.whales.events import (
    POLYMARKET_WHALE_SIGNALS_DERIVED,
    POLYMARKET_WHALE_SIGNALS_FAILED as POLYMARKET_WHALE_SIGNALS_DERIVATION_FAILED,
)
from void_liquidity.adapters.polymarket.signals.whales.events import (
    POLYMARKET_WHALE_SIGNALS_STARTED as POLYMARKET_WHALE_SIGNALS_DERIVATION_STARTED,
)
from void_liquidity.bindings.polymarket.signals import whales as binding_module
from void_liquidity.bindings.polymarket.signals.whales import (
    PolymarketWhaleSignalsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.pipeline.signals.whales import (
    POLYMARKET_WHALE_SIGNALS_COMPLETED,
    POLYMARKET_WHALE_SIGNALS_FAILED,
    POLYMARKET_WHALE_SIGNALS_REQUESTED,
    POLYMARKET_WHALE_SIGNALS_STARTED,
)


def _request() -> DomainEvent:
    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_SIGNALS_REQUESTED,
        source="workflow.whale_market_procurement",
        correlation_id="correlation-signals",
        metadata={"workflow": "whale_market_procurement"},
        payload={"profile": {"name": "high_value"}, "limit": 1},
    )


def _result() -> MarketSignalResult:
    profile = WhaleSignalProfile(name="high_value")
    return MarketSignalResult(
        profile=profile,
        signals=[
            MarketSignal(
                profile=profile.name,
                candidate=_candidate(token_id="token-1"),
                score=100,
                price_delta=0.1,
                price_delta_pct=0.25,
                value_per_wallet=50,
            )
        ],
    )


def test_polymarket_whale_signals_binding_declares_runtime_contract() -> None:
    binding = PolymarketWhaleSignalsBinding()

    assert binding.spec.name == "polymarket.signals.whales"
    assert binding.spec.consumes == (POLYMARKET_WHALE_SIGNALS_REQUESTED,)
    assert binding.spec.produces == (
        POLYMARKET_WHALE_SIGNALS_STARTED,
        POLYMARKET_WHALE_SIGNALS_COMPLETED,
        POLYMARKET_WHALE_SIGNALS_FAILED,
        POLYMARKET_WHALE_SIGNALS_DERIVATION_STARTED,
        POLYMARKET_WHALE_SIGNALS_DERIVED,
        POLYMARKET_WHALE_SIGNALS_DERIVATION_COMPLETED,
        POLYMARKET_WHALE_SIGNALS_DERIVATION_FAILED,
    )


def test_polymarket_whale_signals_binding_derives_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSignalService:
        def __init__(self, profile: WhaleSignalProfile) -> None:
            assert profile.name == "high_value"

        def list(self, *, limit: int | None = None) -> MarketSignalResult:
            assert limit == 1
            return _result()

    monkeypatch.setattr(binding_module, "WhaleSignalService", FakeSignalService)
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    result = asyncio.run(PolymarketWhaleSignalsBinding().handle(_request(), bus))

    assert result == _result()
    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_SIGNALS_STARTED,
        POLYMARKET_WHALE_SIGNALS_DERIVATION_STARTED,
        POLYMARKET_WHALE_SIGNALS_DERIVED,
        POLYMARKET_WHALE_SIGNALS_DERIVATION_COMPLETED,
        POLYMARKET_WHALE_SIGNALS_COMPLETED,
    ]
    assert {event.source for event in emitted_events} == {
        "binding.polymarket.signals.whales"
    }
    assert emitted_events[2].payload["signal_count"] == 1
    assert emitted_events[2].payload["token_ids"] == ["token-1"]


def test_polymarket_whale_signals_binding_publishes_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingSignalService:
        def __init__(self, profile: WhaleSignalProfile) -> None:
            self.profile = profile

        def list(self, *, limit: int | None = None) -> MarketSignalResult:
            raise RuntimeError("signals failed")

    monkeypatch.setattr(binding_module, "WhaleSignalService", FailingSignalService)
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="signals failed"):
        asyncio.run(PolymarketWhaleSignalsBinding().handle(_request(), bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_SIGNALS_STARTED,
        POLYMARKET_WHALE_SIGNALS_DERIVATION_STARTED,
        POLYMARKET_WHALE_SIGNALS_DERIVATION_FAILED,
        POLYMARKET_WHALE_SIGNALS_FAILED,
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
