import asyncio

import pytest

from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_COMPLETED,
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.bindings.polymarket.markets.whales.discovery import (
    PolymarketWhaleDiscoveryBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.workflows import whale_discovery as workflow
from void_liquidity.workflows.whale_discovery import (
    build_whale_discovery_event,
    build_whale_discovery_runtime,
)


def test_build_whale_discovery_event_uses_pipeline_contract() -> None:
    profile = WhaleDiscoveryProfile(wallet_count=3)

    event = build_whale_discovery_event(profile=profile)

    assert event.event_type == POLYMARKET_WHALE_DISCOVERY_REQUESTED
    assert event.source == "workflow.whale_discovery"
    assert event.payload["profile"]["wallet_count"] == 3
    assert event.metadata == {"workflow": "whale_discovery"}


def test_build_whale_discovery_runtime_installs_polymarket_binding() -> None:
    runtime = build_whale_discovery_runtime()

    assert isinstance(
        runtime.registry.get("polymarket.markets.whales.discovery"),
        PolymarketWhaleDiscoveryBinding,
    )


def test_run_whale_discovery_registers_domain_event_logger(
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
                    event_type=POLYMARKET_WHALE_DISCOVERY_COMPLETED,
                    source="fake.runtime",
                    correlation_id=event.correlation_id,
                )
            )

    def fake_build_whale_discovery_runtime(
        bus: EventBus | None = None,
    ) -> FakeRuntime:
        assert bus is not None
        return FakeRuntime(bus=bus)

    monkeypatch.setattr(workflow, "logger", FakeLogger())
    monkeypatch.setattr(
        workflow,
        "build_whale_discovery_runtime",
        fake_build_whale_discovery_runtime,
    )

    asyncio.run(
        workflow.run_whale_discovery(profile=WhaleDiscoveryProfile(wallet_count=3))
    )

    assert [event.event_type for event in logged_events] == [
        POLYMARKET_WHALE_DISCOVERY_REQUESTED,
        POLYMARKET_WHALE_DISCOVERY_COMPLETED,
    ]
    assert logged_events[0].payload["profile"]["wallet_count"] == 3


def test_whale_discovery_main_builds_profile_from_cli_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_profiles: list[WhaleDiscoveryProfile | None] = []

    async def fake_run_whale_discovery(
        *,
        profile: WhaleDiscoveryProfile | None = None,
        echo_events: bool = False,
    ) -> None:
        captured_profiles.append(profile)
        assert echo_events is True

    monkeypatch.setattr(workflow, "run_whale_discovery", fake_run_whale_discovery)

    workflow.main(
        [
            "--wallet-count",
            "3",
            "--trade-window-days",
            "14",
            "--recent-window-days",
            "5",
            "--echo-events",
        ]
    )

    assert captured_profiles[0] is not None
    assert captured_profiles[0].wallet_count == 3
    assert captured_profiles[0].trade_window_days == 14
    assert captured_profiles[0].recent_window_days == 5
