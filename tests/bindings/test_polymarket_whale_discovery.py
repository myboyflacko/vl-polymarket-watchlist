import asyncio
from types import SimpleNamespace

import pytest

from void_liquidity.adapters.polymarket.discovery.whales.domain import (
    WhaleTrackerResult,
)
from void_liquidity.pipeline.discovery.whales.events import WHALE_DISCOVERY_REQUESTED
from void_liquidity.adapters.polymarket.discovery.whales.events import (
    POLYMARKET_WHALES_DISCOVERED,
)
from void_liquidity.core import DomainEvent, EventBus
from void_liquidity.pipeline.discovery.whales.events import (
    WHALE_DISCOVERY_COMPLETED,
    WHALE_DISCOVERY_FAILED,
    WHALE_DISCOVERY_STARTED,
)
from void_liquidity.bindings.polymarket.discovery import whales as binding_module
from void_liquidity.bindings.polymarket.discovery.whales import (
    PolymarketWhaleDiscoveryBinding,
)


def test_polymarket_whale_binding_declares_runtime_contract() -> None:
    binding = PolymarketWhaleDiscoveryBinding()

    assert binding.spec.name == "polymarket.discovery.whales"
    assert binding.spec.consumes == (WHALE_DISCOVERY_REQUESTED,)
    assert "pipeline.discovery.whales.completed" in binding.spec.produces
    assert POLYMARKET_WHALES_DISCOVERED in binding.spec.produces


def test_polymarket_whale_binding_publishes_pipeline_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(
        profile_version="test-profile",
        target_wallet_count=10,
    )

    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, run_id: str, started_at) -> WhaleTrackerResult:
            assert run_id
            assert started_at is not None
            return WhaleTrackerResult(
                whales={"0xabc": {"metadata": {"proxy_wallet": "0xabc"}}},
                candidate_wallet_count=2,
                checked_wallet_count=1,
                accepted_wallet_count=1,
                scoring_method="percentile_v1",
                scoring_criteria={"current_position_value": True},
                request_errors=[],
            )

    monkeypatch.setattr(binding_module, "load_workflow_profile", lambda path=None: profile)
    monkeypatch.setattr(binding_module, "WhaleTracker", FakeTracker)

    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)
    request = DomainEvent.create(
        event_type=WHALE_DISCOVERY_REQUESTED,
        source="workflow.track_whales",
        correlation_id="correlation-1",
        metadata={"workflow": "track_whales"},
    )

    asyncio.run(PolymarketWhaleDiscoveryBinding().handle(event=request, bus=bus))

    assert [event.event_type for event in emitted_events] == [
        WHALE_DISCOVERY_STARTED,
        WHALE_DISCOVERY_COMPLETED,
        POLYMARKET_WHALES_DISCOVERED,
    ]
    assert {event.source for event in emitted_events} == {
        "binding.polymarket.discovery.whales",
    }
    assert {event.correlation_id for event in emitted_events} == {"correlation-1"}
    assert all(
        event.metadata == {
            "workflow": "track_whales",
            "adapter": "polymarket.whales",
            "provider": "polymarket",
        }
        for event in emitted_events
    )
    assert emitted_events[1].payload["candidate_wallet_count"] == 2
    assert emitted_events[1].payload["checked_wallet_count"] == 1
    assert emitted_events[1].payload["accepted_wallet_count"] == 1
    assert emitted_events[1].payload["scoring_method"] == "percentile_v1"
    assert emitted_events[1].payload["scoring_criteria"] == {
        "current_position_value": True,
    }
    assert emitted_events[2].payload["wallets"] == ["0xabc"]
    assert emitted_events[2].payload["scoring_method"] == "percentile_v1"
    assert emitted_events[2].payload["scoring_criteria"] == {
        "current_position_value": True,
    }


def test_polymarket_whale_binding_publishes_failed_event_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(
        profile_version="test-profile",
        target_wallet_count=10,
    )

    class FakeTracker:
        def __init__(self, profile) -> None:
            self.profile = profile

        async def run(self, *, run_id: str, started_at) -> WhaleTrackerResult:
            raise RuntimeError("api down")

    monkeypatch.setattr(binding_module, "load_workflow_profile", lambda path=None: profile)
    monkeypatch.setattr(binding_module, "WhaleTracker", FakeTracker)

    bus = EventBus()
    emitted_events: list[DomainEvent] = []
    bus.subscribe(EventBus.WILDCARD, emitted_events.append)
    request = DomainEvent.create(
        event_type=WHALE_DISCOVERY_REQUESTED,
        source="workflow.track_whales",
        correlation_id="correlation-1",
        metadata={"workflow": "track_whales"},
    )

    with pytest.raises(RuntimeError, match="api down"):
        asyncio.run(PolymarketWhaleDiscoveryBinding().handle(event=request, bus=bus))

    assert [event.event_type for event in emitted_events] == [
        WHALE_DISCOVERY_STARTED,
        WHALE_DISCOVERY_FAILED,
    ]
    failed_event = emitted_events[-1]
    assert failed_event.source == "binding.polymarket.discovery.whales"
    assert failed_event.correlation_id == "correlation-1"
    assert failed_event.payload["error_type"] == "RuntimeError"
    assert failed_event.payload["error"] == "api down"
    assert failed_event.metadata == {
        "workflow": "track_whales",
        "adapter": "polymarket.whales",
        "provider": "polymarket",
    }
