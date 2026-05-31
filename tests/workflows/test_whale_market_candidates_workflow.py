import asyncio

import pytest

from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALES_V2_REQUESTED,
)
from void_liquidity.adapters.polymarket.markets.whales.candidates.collector import (
    DEFAULT_MIN_WHALE_COUNT,
)
from void_liquidity.bindings.polymarket.discovery.whales_v2 import (
    PolymarketWhaleDiscoveryV2Binding,
)
from void_liquidity.bindings.polymarket.markets.whales import (
    PolymarketWhaleMarketsBinding,
)
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_COMPLETED,
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.workflows import whale_market_candidates as workflow
from void_liquidity.workflows.whale_market_candidates import (
    build_whale_market_candidates_event,
    build_whale_market_candidates_runtime,
)


def test_build_whale_market_candidates_event_uses_pipeline_contract() -> None:
    event = build_whale_market_candidates_event()

    assert event.event_type == POLYMARKET_WHALE_MARKETS_REQUESTED
    assert event.source == "workflow.whale_market_candidates"
    assert event.payload == {}
    assert event.metadata == {"workflow": "whale_market_candidates"}


def test_build_whale_market_candidates_runtime_installs_polymarket_binding() -> None:
    runtime = build_whale_market_candidates_runtime()

    assert isinstance(
        runtime.registry.get("polymarket.markets.whales.discovery"),
        PolymarketWhaleDiscoveryV2Binding,
    )
    assert isinstance(
        runtime.registry.get("polymarket.markets.whales"),
        PolymarketWhaleMarketsBinding,
    )


def test_run_whale_market_candidates_registers_domain_event_logger(
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
            if event.event_type == POLYMARKET_WHALE_MARKETS_REQUESTED:
                await self.bus.publish(
                    DomainEvent.create(
                        event_type=POLYMARKET_WHALE_MARKETS_COMPLETED,
                        source="fake.runtime",
                        correlation_id=event.correlation_id,
                    )
                )

    def fake_build_whale_market_candidates_runtime(
        *,
        bus: EventBus | None = None,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> FakeRuntime:
        assert bus is not None
        assert min_whale_count == DEFAULT_MIN_WHALE_COUNT
        return FakeRuntime(bus=bus)

    monkeypatch.setattr(workflow, "logger", FakeLogger())
    monkeypatch.setattr(
        workflow,
        "build_whale_market_candidates_runtime",
        fake_build_whale_market_candidates_runtime,
    )

    asyncio.run(workflow.run_whale_market_candidates())

    assert [event.event_type for event in logged_events] == [
        POLYMARKET_WHALES_V2_REQUESTED,
        POLYMARKET_WHALE_MARKETS_REQUESTED,
        POLYMARKET_WHALE_MARKETS_COMPLETED,
    ]


def test_run_whale_market_candidates_supports_echo_events(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeRuntime:
        def __init__(self, bus: EventBus) -> None:
            self.bus = bus

        async def publish(self, event: DomainEvent) -> None:
            await self.bus.publish(event)
            if event.event_type == POLYMARKET_WHALE_MARKETS_REQUESTED:
                await self.bus.publish(
                    DomainEvent.create(
                        event_type=POLYMARKET_WHALE_MARKETS_COMPLETED,
                        source="fake.runtime",
                        correlation_id=event.correlation_id,
                    )
                )

    def fake_build_whale_market_candidates_runtime(
        *,
        bus: EventBus | None = None,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> FakeRuntime:
        assert bus is not None
        assert min_whale_count == DEFAULT_MIN_WHALE_COUNT
        return FakeRuntime(bus=bus)

    monkeypatch.setattr(
        workflow,
        "build_whale_market_candidates_runtime",
        fake_build_whale_market_candidates_runtime,
    )

    asyncio.run(workflow.run_whale_market_candidates(echo_events=True))

    assert POLYMARKET_WHALE_MARKETS_COMPLETED in capsys.readouterr().out


def test_run_whale_market_candidates_passes_min_whale_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_min_whale_count: list[int] = []

    class FakeRuntime:
        async def publish(self, event: DomainEvent) -> None:
            return None

    def fake_build_whale_market_candidates_runtime(
        *,
        bus: EventBus | None = None,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> FakeRuntime:
        assert bus is not None
        captured_min_whale_count.append(min_whale_count)
        return FakeRuntime()

    monkeypatch.setattr(
        workflow,
        "build_whale_market_candidates_runtime",
        fake_build_whale_market_candidates_runtime,
    )

    asyncio.run(workflow.run_whale_market_candidates(min_whale_count=4))

    assert captured_min_whale_count == [4]


def test_whale_market_candidates_main_runs_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_args: list[dict[str, bool | int]] = []

    async def fake_run_whale_market_candidates(
        *,
        echo_events: bool = False,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> None:
        captured_args.append(
            {
                "echo_events": echo_events,
                "min_whale_count": min_whale_count,
            }
        )

    monkeypatch.setattr(
        workflow,
        "run_whale_market_candidates",
        fake_run_whale_market_candidates,
    )

    workflow.main(["--echo-events", "--min-whale-count", "4"])

    assert captured_args == [
        {
            "echo_events": True,
            "min_whale_count": 4,
        }
    ]
