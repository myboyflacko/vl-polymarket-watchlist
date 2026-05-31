import asyncio
from datetime import UTC, datetime

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
    WalletCollectionError,
    Whales,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_COMPLETED,
    POLYMARKET_WHALE_DISCOVERY_DISCOVERED,
    POLYMARKET_WHALE_DISCOVERY_FAILED,
    POLYMARKET_WHALE_DISCOVERY_PERSIST_COMPLETED,
    POLYMARKET_WHALE_DISCOVERY_PERSIST_FAILED,
    POLYMARKET_WHALE_DISCOVERY_PERSIST_STARTED,
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
    POLYMARKET_WHALE_DISCOVERY_STARTED,
)
from void_liquidity.bindings.polymarket.markets.whales import discovery as binding_module
from void_liquidity.bindings.polymarket.markets.whales.discovery import (
    PolymarketWhaleDiscoveryBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus


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
        event_type=POLYMARKET_WHALE_DISCOVERY_REQUESTED,
        source="workflow.whale_discovery",
        correlation_id="correlation-discovery",
        metadata={"workflow": "whale_discovery"},
        payload={"profile": {"wallet_count": 1}},
    )


def _partial_whales() -> Whales:
    whales = _whales()
    return whales.model_copy(
        update={
            "collection_errors": [
                WalletCollectionError(
                    proxy_wallet="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    stage="trades",
                    error_type="RuntimeError",
                    error="api down",
                )
            ]
        }
    )


def test_polymarket_whale_discovery_binding_declares_runtime_contract() -> None:
    binding = PolymarketWhaleDiscoveryBinding()

    assert binding.spec.name == "polymarket.markets.whales.discovery"
    assert binding.spec.consumes == (POLYMARKET_WHALE_DISCOVERY_REQUESTED,)
    assert POLYMARKET_WHALE_DISCOVERY_COMPLETED in binding.spec.produces
    assert POLYMARKET_WHALE_DISCOVERY_PERSIST_COMPLETED in binding.spec.produces


def test_polymarket_whale_discovery_binding_runs_persists_and_publishes(
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

    monkeypatch.setattr(binding_module, "WhaleDiscoveryService", FakeTracker)

    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    asyncio.run(PolymarketWhaleDiscoveryBinding().handle(event=_request(), bus=bus))

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_DISCOVERY_STARTED,
        POLYMARKET_WHALE_DISCOVERY_DISCOVERED,
        POLYMARKET_WHALE_DISCOVERY_PERSIST_STARTED,
        POLYMARKET_WHALE_DISCOVERY_PERSIST_COMPLETED,
        POLYMARKET_WHALE_DISCOVERY_COMPLETED,
    ]
    assert persisted
    assert "ranking_result" not in persisted[0]
    assert {event.source for event in emitted_events} == {
        "binding.polymarket.markets.whales.discovery"
    }
    assert {event.correlation_id for event in emitted_events} == {"correlation-discovery"}
    assert emitted_events[-1].payload["collected_wallet_count"] == 1
    assert "ranked_wallet_count" not in emitted_events[-1].payload
    assert "ranking_method" not in emitted_events[-1].payload
    assert "ranked_wallets" not in emitted_events[-1].payload
    assert emitted_events[-1].payload["failed_wallet_count"] == 0
    assert emitted_events[-1].payload["partial"] is False


def test_polymarket_whale_discovery_binding_does_not_rank_before_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[dict] = []

    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, now: datetime | None = None) -> Whales:
            return _whales()

        def persist(self, **kwargs) -> None:
            persisted.append(kwargs)

    monkeypatch.setattr(binding_module, "WhaleDiscoveryService", FakeTracker)
    bus = EventBus()

    asyncio.run(PolymarketWhaleDiscoveryBinding().handle(event=_request(), bus=bus))

    assert persisted
    assert "ranking_result" not in persisted[0]


def test_polymarket_whale_discovery_binding_publishes_partial_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, now: datetime | None = None) -> Whales:
            return _partial_whales()

        def persist(self, **kwargs) -> None:
            return None

    monkeypatch.setattr(binding_module, "WhaleDiscoveryService", FakeTracker)
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    asyncio.run(PolymarketWhaleDiscoveryBinding().handle(event=_request(), bus=bus))

    completed = emitted_events[-1]
    assert completed.payload["partial"] is True
    assert completed.payload["failed_wallet_count"] == 1
    assert completed.payload["collection_error_count"] == 1


def test_polymarket_whale_discovery_binding_publishes_failed_event_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, now: datetime | None = None) -> Whales:
            raise RuntimeError("api down")

    monkeypatch.setattr(binding_module, "WhaleDiscoveryService", FakeTracker)
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="api down"):
        asyncio.run(
            PolymarketWhaleDiscoveryBinding().handle(event=_request(), bus=bus)
        )

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_DISCOVERY_STARTED,
        POLYMARKET_WHALE_DISCOVERY_FAILED,
    ]
    assert emitted_events[-1].payload["error_type"] == "RuntimeError"


def test_polymarket_whale_discovery_binding_publishes_persist_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, now: datetime | None = None) -> Whales:
            return _whales()

        def persist(self, **kwargs) -> None:
            raise RuntimeError("db down")

    monkeypatch.setattr(binding_module, "WhaleDiscoveryService", FakeTracker)
    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)

    with pytest.raises(RuntimeError, match="db down"):
        asyncio.run(
            PolymarketWhaleDiscoveryBinding().handle(event=_request(), bus=bus)
        )

    assert [event.event_type for event in emitted_events] == [
        POLYMARKET_WHALE_DISCOVERY_STARTED,
        POLYMARKET_WHALE_DISCOVERY_DISCOVERED,
        POLYMARKET_WHALE_DISCOVERY_PERSIST_STARTED,
        POLYMARKET_WHALE_DISCOVERY_PERSIST_FAILED,
        POLYMARKET_WHALE_DISCOVERY_FAILED,
    ]
    assert emitted_events[-2].payload["error"] == "db down"
