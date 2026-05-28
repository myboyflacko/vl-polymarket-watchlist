from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence

from void_liquidity.adapters.polymarket.markets.whales.events import (
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)
from void_liquidity.bindings.polymarket import PolymarketWhaleMarketsBinding
from void_liquidity.core import DomainEvent, EventBus, Runtime
from void_liquidity.logging import VoidLogger


logger = VoidLogger("void_liquidity.workflows.whale_market_candidates")


def build_whale_market_candidates_event(
    *,
    source: str = "workflow.whale_market_candidates",
) -> DomainEvent:
    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_MARKETS_REQUESTED,
        source=source,
        payload={},
        metadata={"workflow": "whale_market_candidates"},
    )


def build_whale_market_candidates_runtime(bus: EventBus | None = None) -> Runtime:
    runtime = Runtime(bus=bus)
    runtime.install(PolymarketWhaleMarketsBinding())
    return runtime


async def run_whale_market_candidates(*, echo_events: bool = False) -> None:
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, logger.log_domain_event)

    if echo_events:
        bus.subscribe(EventBus.WILDCARD, _print_event)

    runtime = build_whale_market_candidates_runtime(bus=bus)
    await runtime.publish(build_whale_market_candidates_event())


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run Polymarket whale market candidate discovery.",
    )
    parser.add_argument(
        "--echo-events",
        action="store_true",
        help="Print emitted runtime events as JSON lines.",
    )
    args = parser.parse_args(argv)

    asyncio.run(run_whale_market_candidates(echo_events=args.echo_events))


def _print_event(event: DomainEvent) -> None:
    print(
        json.dumps(
            {
                "event_type": event.event_type,
                "source": event.source,
                "correlation_id": event.correlation_id,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": event.payload,
                "metadata": event.metadata,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
