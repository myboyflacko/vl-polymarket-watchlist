import asyncio

import pytest

from void_liquidity.adapters.polymarket.discovery.whales.events import (
    POLYMARKET_WHALES_V2_COMPLETED,
    POLYMARKET_WHALES_V2_REQUESTED,
)
from void_liquidity.adapters.polymarket.discovery.whales.profiles import (
    WhaleTrackerV2Profile,
)
from void_liquidity.bindings.polymarket.discovery.whales_v2 import (
    PolymarketWhaleDiscoveryV2Binding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.workflows import track_whales_v2 as workflow
from void_liquidity.workflows.track_whales_v2 import (
    build_track_whales_v2_event,
    build_track_whales_v2_runtime,
)


def test_build_track_whales_v2_event_uses_pipeline_contract() -> None:
    profile = WhaleTrackerV2Profile(wallet_count=3)

    event = build_track_whales_v2_event(profile=profile)

    assert event.event_type == POLYMARKET_WHALES_V2_REQUESTED
    assert event.source == "workflow.track_whales_v2"
    assert event.payload["profile"]["wallet_count"] == 3
    assert event.metadata == {"workflow": "track_whales_v2"}


def test_build_track_whales_v2_runtime_installs_polymarket_binding() -> None:
    runtime = build_track_whales_v2_runtime()

    assert isinstance(
        runtime.registry.get("polymarket.discovery.whales_v2"),
        PolymarketWhaleDiscoveryV2Binding,
    )


def test_run_track_whales_v2_registers_domain_event_logger(
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
                    event_type=POLYMARKET_WHALES_V2_COMPLETED,
                    source="fake.runtime",
                    correlation_id=event.correlation_id,
                )
            )

    def fake_build_track_whales_v2_runtime(
        bus: EventBus | None = None,
    ) -> FakeRuntime:
        assert bus is not None
        return FakeRuntime(bus=bus)

    monkeypatch.setattr(workflow, "logger", FakeLogger())
    monkeypatch.setattr(
        workflow,
        "build_track_whales_v2_runtime",
        fake_build_track_whales_v2_runtime,
    )

    asyncio.run(
        workflow.run_track_whales_v2(profile=WhaleTrackerV2Profile(wallet_count=3))
    )

    assert [event.event_type for event in logged_events] == [
        POLYMARKET_WHALES_V2_REQUESTED,
        POLYMARKET_WHALES_V2_COMPLETED,
    ]
    assert logged_events[0].payload["profile"]["wallet_count"] == 3


def test_track_whales_v2_main_builds_profile_from_cli_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_profiles: list[WhaleTrackerV2Profile | None] = []

    async def fake_run_track_whales_v2(
        *,
        profile: WhaleTrackerV2Profile | None = None,
        echo_events: bool = False,
    ) -> None:
        captured_profiles.append(profile)
        assert echo_events is True

    monkeypatch.setattr(workflow, "run_track_whales_v2", fake_run_track_whales_v2)

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
