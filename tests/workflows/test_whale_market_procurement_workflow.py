import asyncio

import pytest

from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.adapters.polymarket.signals.whales.domain import WhaleSignalProfile
from void_liquidity.bindings.polymarket.markets.whales.candidates import (
    PolymarketWhaleMarketCandidatesBinding,
)
from void_liquidity.bindings.polymarket.markets.whales.discovery import (
    PolymarketWhaleDiscoveryBinding,
)
from void_liquidity.bindings.polymarket.signals.whales import (
    PolymarketWhaleSignalsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.runtime import Runtime
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)
from void_liquidity.pipeline.signals.whales import (
    POLYMARKET_WHALE_SIGNALS_REQUESTED,
)
from void_liquidity.workflows import whale_market_procurement as workflow


def test_build_whale_market_procurement_runtime_installs_bindings() -> None:
    runtime = workflow.build_whale_market_procurement_runtime()

    assert isinstance(
        runtime.registry.get("polymarket.markets.whales.discovery"),
        PolymarketWhaleDiscoveryBinding,
    )
    assert isinstance(
        runtime.registry.get("polymarket.markets.whales.candidates"),
        PolymarketWhaleMarketCandidatesBinding,
    )
    assert isinstance(
        runtime.registry.get("polymarket.signals.whales"),
        PolymarketWhaleSignalsBinding,
    )


def test_build_whale_market_procurement_scheduler_registers_process_order() -> None:
    runtime = Runtime()
    scheduler = workflow.build_whale_market_procurement_scheduler(
        runtime=runtime,
        discovery_profile=WhaleDiscoveryProfile(wallet_count=3),
        signal_profiles=(WhaleSignalProfile(name="confirmed"),),
        signal_limit=2,
    )

    assert [job.name for job in scheduler.registry] == [
        "whales.discover",
        "whales.market_candidates",
        "whales.signals.confirmed",
    ]

    events = [job.event_factory() for job in scheduler.registry]
    assert [event.event_type for event in events] == [
        POLYMARKET_WHALE_DISCOVERY_REQUESTED,
        POLYMARKET_WHALE_MARKETS_REQUESTED,
        POLYMARKET_WHALE_SIGNALS_REQUESTED,
    ]
    assert events[0].payload["profile"]["wallet_count"] == 3
    assert events[2].payload["profile"]["name"] == "confirmed"
    assert events[2].payload["limit"] == 2


def test_run_whale_market_procurement_uses_scheduler_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_events: list[DomainEvent] = []

    class FakeRuntime:
        def __init__(self, bus: EventBus) -> None:
            self.bus = bus

        async def publish(self, event: DomainEvent) -> None:
            published_events.append(event)
            await self.bus.publish(event)

    def fake_build_runtime(
        *,
        bus: EventBus | None = None,
        min_whale_count: int,
    ) -> FakeRuntime:
        assert bus is not None
        assert min_whale_count == 4
        return FakeRuntime(bus=bus)

    monkeypatch.setattr(
        workflow,
        "build_whale_market_procurement_runtime",
        fake_build_runtime,
    )

    asyncio.run(
        workflow.run_whale_market_procurement(
            min_whale_count=4,
            signal_profiles=(WhaleSignalProfile(name="pain"),),
            signal_limit=1,
        )
    )

    assert [event.event_type for event in published_events] == [
        POLYMARKET_WHALE_DISCOVERY_REQUESTED,
        POLYMARKET_WHALE_MARKETS_REQUESTED,
        POLYMARKET_WHALE_SIGNALS_REQUESTED,
    ]
    assert published_events[-1].payload["profile"]["name"] == "pain"
    assert published_events[-1].payload["limit"] == 1


def test_whale_market_procurement_main_builds_cli_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict] = []

    async def fake_run_whale_market_procurement(**kwargs) -> None:
        captured.append(kwargs)

    monkeypatch.setattr(
        workflow,
        "run_whale_market_procurement",
        fake_run_whale_market_procurement,
    )

    workflow.main(
        [
            "--wallet-count",
            "3",
            "--min-whale-count",
            "4",
            "--signal-profile",
            "confirmed",
            "--signal-limit",
            "2",
            "--echo-events",
        ]
    )

    assert captured[0]["discovery_profile"] == WhaleDiscoveryProfile(wallet_count=3)
    assert captured[0]["min_whale_count"] == 4
    assert captured[0]["signal_profiles"] == (
        WhaleSignalProfile(name="confirmed"),
    )
    assert captured[0]["signal_limit"] == 2
    assert captured[0]["echo_events"] is True
