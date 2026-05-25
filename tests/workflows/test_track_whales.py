import asyncio
from pathlib import Path

import pytest

from void_liquidity.core import DomainEvent, EventBus
from void_liquidity.pipeline.discovery.whales import WHALE_DISCOVERY_REQUESTED
from void_liquidity.bindings.polymarket import PolymarketWhaleDiscoveryBinding
from void_liquidity.workflows import track_whales as workflow
from void_liquidity.workflows.track_whales import (
    build_track_whales_event,
    build_track_whales_runtime,
)


def test_build_track_whales_event_uses_pipeline_contract() -> None:
    event = build_track_whales_event(profile_path=Path("profile.json"))

    assert event.event_type == WHALE_DISCOVERY_REQUESTED
    assert event.source == "workflow.track_whales"
    assert event.payload == {"profile_path": "profile.json"}
    assert event.metadata == {"workflow": "track_whales"}


def test_build_track_whales_runtime_installs_polymarket_binding() -> None:
    runtime = build_track_whales_runtime()

    assert isinstance(
        runtime.registry.get("polymarket.discovery.whales"),
        PolymarketWhaleDiscoveryBinding,
    )


def test_run_track_whales_registers_domain_event_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged_events: list[DomainEvent] = []

    class FakeLogger:
        def log_domain_event(self, event: DomainEvent) -> None:
            logged_events.append(event)

    class FakeRuntime:
        def __init__(self, bus: EventBus) -> None:
            self.bus = bus

        async def publish(self, event: DomainEvent) -> None:
            await self.bus.publish(event)
            await self.bus.publish(
                DomainEvent.create(
                    event_type="pipeline.discovery.whales.completed",
                    source="fake.runtime",
                    correlation_id=event.correlation_id,
                )
            )

    def fake_build_track_whales_runtime(bus: EventBus | None = None) -> FakeRuntime:
        assert bus is not None
        return FakeRuntime(bus=bus)

    monkeypatch.setattr(workflow, "logger", FakeLogger())
    monkeypatch.setattr(
        workflow,
        "build_track_whales_runtime",
        fake_build_track_whales_runtime,
    )

    asyncio.run(workflow.run_track_whales(profile_path=Path("profile.json")))

    assert [event.event_type for event in logged_events] == [
        WHALE_DISCOVERY_REQUESTED,
        "pipeline.discovery.whales.completed",
    ]
    assert logged_events[0].payload == {"profile_path": "profile.json"}
