import asyncio

import pytest

from void_liquidity.adapters.polymarket.markets.whales.discovery.domain import (
    CollectionQuality,
    ExposureMetrics,
    LeaderboardMetrics,
    MarketMetrics,
    TradeMetrics,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.events import (
    POLYMARKET_WHALE_SELECTION_COMPLETED,
    POLYMARKET_WHALE_SELECTION_FAILED,
    POLYMARKET_WHALE_SELECTION_SELECTED,
    POLYMARKET_WHALE_SELECTION_SKIPPED,
    POLYMARKET_WHALE_SELECTION_STARTED,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.ranking import (
    DEFAULT_TRADE_FIRST_RANKING_METHOD,
    RankedWhale,
    WhaleSelectionRankingResult,
)
from void_liquidity.bindings.polymarket.markets.whales import selection as binding_module
from void_liquidity.bindings.polymarket.markets.whales.selection import (
    PolymarketWhaleSelectionBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus


def _request() -> DomainEvent:
    return DomainEvent.create(
        event_type="pipeline.markets.whales.selection.requested",
        source="workflow.whale_selection",
        correlation_id="correlation-selection",
        metadata={"workflow": "whale_selection"},
        payload={
            "profile": {"bottom_cut_percentile": 0},
            "discovery_run_id": "discovery-run-1",
        },
    )


def _result() -> WhaleSelectionRankingResult:
    return WhaleSelectionRankingResult(
        method=DEFAULT_TRADE_FIRST_RANKING_METHOD,
        ranked_whales=[RankedWhale(whale=_whale("wallet-high"), score=1.0)],
        removed_whales=[RankedWhale(whale=_whale("wallet-low"), score=0.1)],
    )


def test_polymarket_whale_selection_binding_declares_runtime_contract() -> None:
    binding = PolymarketWhaleSelectionBinding()

    assert binding.spec.name == "polymarket.markets.whales.selection"
    assert binding.spec.consumes == ("polymarket.markets.whales.selection.requested",)
    assert binding.spec.produces == (
        POLYMARKET_WHALE_SELECTION_STARTED,
        POLYMARKET_WHALE_SELECTION_SELECTED,
        POLYMARKET_WHALE_SELECTION_COMPLETED,
        POLYMARKET_WHALE_SELECTION_FAILED,
        POLYMARKET_WHALE_SELECTION_SKIPPED,
    )


def test_polymarket_whale_selection_binding_selects_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSelectionService:
        def __init__(self, profile) -> None:
            assert profile is not None

        def run(self, *, discovery_run_id: str | None = None) -> WhaleSelectionRankingResult:
            return _result()

        def persist(self, **kwargs) -> None:
            return None

    monkeypatch.setattr(binding_module, "WhaleSelectionService", FakeSelectionService)
    monkeypatch.setattr(
        binding_module,
        "get_completed_selection_run_for_parent",
        lambda **_: None,
    )
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    result = asyncio.run(PolymarketWhaleSelectionBinding().handle(_request(), bus))

    assert result == _result()
    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_SELECTION_STARTED,
        POLYMARKET_WHALE_SELECTION_SELECTED,
        POLYMARKET_WHALE_SELECTION_COMPLETED,
    ]
    assert {event.source for event in emitted_events} == {
        "binding.polymarket.markets.whales.selection"
    }
    assert {event.correlation_id for event in emitted_events} == {
        "correlation-selection"
    }
    selected = emitted_events[1].payload
    assert selected["ranked_wallet_count"] == 1
    assert selected["removed_wallet_count"] == 1
    assert selected["ranked_wallets"] == ["wallet-high"]
    assert selected["removed_wallets"] == ["wallet-low"]


def test_polymarket_whale_selection_binding_publishes_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingSelectionService:
        def __init__(self, profile) -> None:
            self.profile = profile

        def run(self, *, discovery_run_id: str | None = None) -> WhaleSelectionRankingResult:
            raise RuntimeError("selection failed")

    monkeypatch.setattr(binding_module, "WhaleSelectionService", FailingSelectionService)
    monkeypatch.setattr(
        binding_module,
        "get_completed_selection_run_for_parent",
        lambda **_: None,
    )
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="selection failed"):
        asyncio.run(PolymarketWhaleSelectionBinding().handle(_request(), bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_SELECTION_STARTED,
        POLYMARKET_WHALE_SELECTION_FAILED,
    ]
    assert emitted_events[-1].payload["error_type"] == "RuntimeError"
    assert emitted_events[-1].payload["error"] == "selection failed"


def _whale(proxy_wallet: str) -> Whale:
    return Whale(
        identity=WhaleIdentity(proxy_wallet=proxy_wallet),
        metrics=WhaleMetrics(
            leaderboard=LeaderboardMetrics(candidate_source="both"),
            trades=TradeMetrics(),
            markets=MarketMetrics(),
            exposure=ExposureMetrics(),
            collection_quality=CollectionQuality(),
        ),
    )
