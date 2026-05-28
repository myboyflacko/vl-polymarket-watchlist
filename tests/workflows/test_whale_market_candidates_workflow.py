import asyncio

import pytest

from void_liquidity.adapters.polymarket.markets.whales.events import (
    POLYMARKET_WHALE_MARKETS_COMPLETED,
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)
from void_liquidity.bindings.polymarket import PolymarketWhaleMarketsBinding
from void_liquidity.core import DomainEvent, EventBus
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
            await self.bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_COMPLETED,
                    source="fake.runtime",
                    correlation_id=event.correlation_id,
                )
            )

    def fake_build_whale_market_candidates_runtime(
        bus: EventBus | None = None,
    ) -> FakeRuntime:
        assert bus is not None
        return FakeRuntime(bus=bus)

    monkeypatch.setattr(workflow, "logger", FakeLogger())
    monkeypatch.setattr(
        workflow,
        "build_whale_market_candidates_runtime",
        fake_build_whale_market_candidates_runtime,
    )

    asyncio.run(workflow.run_whale_market_candidates())

    assert [event.event_type for event in logged_events] == [
        POLYMARKET_WHALE_MARKETS_REQUESTED,
        POLYMARKET_WHALE_MARKETS_COMPLETED,
    ]


def test_whale_market_candidates_main_runs_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_echo_events: list[bool] = []

    async def fake_run_whale_market_candidates(*, echo_events: bool = False) -> None:
        captured_echo_events.append(echo_events)

    monkeypatch.setattr(
        workflow,
        "run_whale_market_candidates",
        fake_run_whale_market_candidates,
    )

    workflow.main(["--echo-events"])

    assert captured_echo_events == [True]
