import asyncio
import json

import pytest

from void_liquidity.adapters.polymarket.markets.whales.domain import (
    MarketCandidate,
    WhaleMarketCandidates,
)
from void_liquidity.adapters.polymarket.markets.whales.collector import (
    DEFAULT_MIN_WHALE_COUNT,
)
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_COMPLETED,
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)
from void_liquidity.bindings.polymarket.markets.whales import (
    PolymarketWhaleMarketsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.workflows import whale_market_candidates as workflow
from void_liquidity.workflows.whale_market_candidates import (
    build_whale_market_candidates_event,
    build_whale_market_candidates_runtime,
)


def _result() -> WhaleMarketCandidates:
    return WhaleMarketCandidates(
        candidates=[
            MarketCandidate(
                token_id="token-1",
                condition_id="0x" + "1" * 64,
                title="Will this happen?",
                slug="will-this-happen",
                outcome="Yes",
                whale_count=2,
                wallets=["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
                total_size=10,
                total_current_value=100,
                weighted_avg_price=0.4,
                cur_price=0.5,
            )
        ]
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
    capsys: pytest.CaptureFixture[str],
) -> None:
    logged_events: list[DomainEvent] = []

    class FakeLogger:
        def log_domain_event(self, event: DomainEvent) -> None:
            logged_events.append(event)

    class FakeBinding:
        def __init__(
            self,
            *,
            min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
        ) -> None:
            self.min_whale_count = min_whale_count

        async def handle(
            self,
            event: DomainEvent,
            bus: EventBus,
        ) -> WhaleMarketCandidates:
            assert self.min_whale_count == DEFAULT_MIN_WHALE_COUNT
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_COMPLETED,
                    source="fake.runtime",
                    correlation_id=event.correlation_id,
                )
            )
            return _result()

    monkeypatch.setattr(workflow, "logger", FakeLogger())
    monkeypatch.setattr(
        workflow,
        "PolymarketWhaleMarketsBinding",
        FakeBinding,
    )

    asyncio.run(workflow.run_whale_market_candidates())

    printed = json.loads(capsys.readouterr().out)
    assert printed["candidate_count"] == 1
    assert printed["candidates"][0]["token_id"] == "token-1"
    assert [event.event_type for event in logged_events] == [
        POLYMARKET_WHALE_MARKETS_REQUESTED,
        POLYMARKET_WHALE_MARKETS_COMPLETED,
    ]


def test_whale_market_candidates_main_runs_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_args: list[dict[str, bool]] = []

    async def fake_run_whale_market_candidates(
        *,
        echo_events: bool = False,
        print_candidates: bool = True,
        min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    ) -> None:
        captured_args.append(
            {
                "echo_events": echo_events,
                "print_candidates": print_candidates,
                "min_whale_count": min_whale_count,
            }
        )

    monkeypatch.setattr(
        workflow,
        "run_whale_market_candidates",
        fake_run_whale_market_candidates,
    )

    workflow.main(["--echo-events", "--no-print-candidates", "--min-whale-count", "4"])

    assert captured_args == [
        {
            "echo_events": True,
            "print_candidates": False,
            "min_whale_count": 4,
        }
    ]
