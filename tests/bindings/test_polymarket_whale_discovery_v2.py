import asyncio
from datetime import UTC, datetime

import pytest

from void_liquidity.adapters.polymarket.discovery.whales_v2.domain import (
    CollectionQuality,
    ExposureMetrics,
    LeaderboardMetrics,
    MarketMetrics,
    TradeMetrics,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    Whales,
)
from void_liquidity.adapters.polymarket.discovery.whales_v2.events import (
    POLYMARKET_WHALES_V2_COMPLETED,
    POLYMARKET_WHALES_V2_DISCOVERED,
    POLYMARKET_WHALES_V2_FAILED,
    POLYMARKET_WHALES_V2_PERSIST_COMPLETED,
    POLYMARKET_WHALES_V2_PERSIST_FAILED,
    POLYMARKET_WHALES_V2_PERSIST_STARTED,
    POLYMARKET_WHALES_V2_REQUESTED,
    POLYMARKET_WHALES_V2_STARTED,
)
from void_liquidity.bindings.polymarket.discovery import whales_v2 as binding_module
from void_liquidity.bindings.polymarket.discovery.whales_v2 import (
    PolymarketWhaleDiscoveryV2Binding,
)
from void_liquidity.core import DomainEvent, EventBus


NOW = datetime(2026, 5, 26, tzinfo=UTC)


def _whales() -> Whales:
    return Whales(
        whales=[
            Whale(
                identity=WhaleIdentity(
                    proxy_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                ),
                metrics=WhaleMetrics(
                    leaderboard=LeaderboardMetrics(
                        leaderboard_pnl_month=100,
                        leaderboard_volume_month=1_000,
                        candidate_source="both",
                    ),
                    trades=TradeMetrics(trade_volume_30d=1_000),
                    markets=MarketMetrics(),
                    exposure=ExposureMetrics(),
                    collection_quality=CollectionQuality(),
                ),
            )
        ],
        candidate_wallet_count=1,
        checked_wallet_count=1,
        generated_at=NOW,
        profile_version="test",
    )


def _request() -> DomainEvent:
    return DomainEvent.create(
        event_type=POLYMARKET_WHALES_V2_REQUESTED,
        source="workflow.track_whales_v2",
        correlation_id="correlation-v2",
        metadata={"workflow": "track_whales_v2"},
        payload={"profile": {"wallet_count": 1}},
    )


def test_polymarket_whale_v2_binding_declares_runtime_contract() -> None:
    binding = PolymarketWhaleDiscoveryV2Binding()

    assert binding.spec.name == "polymarket.discovery.whales_v2"
    assert binding.spec.consumes == (POLYMARKET_WHALES_V2_REQUESTED,)
    assert POLYMARKET_WHALES_V2_COMPLETED in binding.spec.produces
    assert POLYMARKET_WHALES_V2_PERSIST_COMPLETED in binding.spec.produces


def test_polymarket_whale_v2_binding_runs_scores_persists_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[dict] = []

    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, now: datetime | None = None) -> Whales:
            assert now is not None
            return _whales()

        def persist(self, **kwargs) -> None:
            persisted.append(kwargs)

    monkeypatch.setattr(binding_module, "WhaleTrackerV2", FakeTracker)

    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    asyncio.run(PolymarketWhaleDiscoveryV2Binding().handle(event=_request(), bus=bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALES_V2_STARTED,
        POLYMARKET_WHALES_V2_DISCOVERED,
        POLYMARKET_WHALES_V2_PERSIST_STARTED,
        POLYMARKET_WHALES_V2_PERSIST_COMPLETED,
        POLYMARKET_WHALES_V2_COMPLETED,
    ]
    assert persisted
    assert persisted[0]["ranking_result"].method == "trade_first_percentile_v1"
    assert emitted_events[-1].payload["ranking_method"] == "trade_first_percentile_v1"
    assert emitted_events[-1].payload["ranked_wallets"] == [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ]
    assert {event.source for event in emitted_events} == {
        "binding.polymarket.discovery.whales_v2"
    }
    assert {event.correlation_id for event in emitted_events} == {"correlation-v2"}


def test_polymarket_whale_v2_binding_publishes_failed_event_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, now: datetime | None = None) -> Whales:
            raise RuntimeError("api down")

    monkeypatch.setattr(binding_module, "WhaleTrackerV2", FakeTracker)
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="api down"):
        asyncio.run(PolymarketWhaleDiscoveryV2Binding().handle(event=_request(), bus=bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALES_V2_STARTED,
        POLYMARKET_WHALES_V2_FAILED,
    ]
    assert emitted_events[-1].payload["error_type"] == "RuntimeError"


def test_polymarket_whale_v2_binding_publishes_persist_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, now: datetime | None = None) -> Whales:
            return _whales()

        def persist(self, **kwargs) -> None:
            raise RuntimeError("db down")

    monkeypatch.setattr(binding_module, "WhaleTrackerV2", FakeTracker)
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="db down"):
        asyncio.run(PolymarketWhaleDiscoveryV2Binding().handle(event=_request(), bus=bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALES_V2_STARTED,
        POLYMARKET_WHALES_V2_DISCOVERED,
        POLYMARKET_WHALES_V2_PERSIST_STARTED,
        POLYMARKET_WHALES_V2_PERSIST_FAILED,
        POLYMARKET_WHALES_V2_FAILED,
    ]
    assert emitted_events[-2].payload["error"] == "db down"
