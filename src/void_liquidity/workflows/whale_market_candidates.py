from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from typing import Sequence

from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
)
from void_liquidity.adapters.polymarket.markets.whales.candidates.collector import (
    DEFAULT_MIN_WHALE_COUNT,
)
from void_liquidity.bindings.polymarket.markets.whales.discovery import (
    PolymarketWhaleDiscoveryBinding,
)
from void_liquidity.bindings.polymarket.markets.whales import (
    PolymarketWhaleMarketsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.runtime import Runtime
from void_liquidity.core.logging import VoidLogger
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)

from void_liquidity.core.scheduler import ScheduledJob, Scheduler


logger = VoidLogger("void_liquidity.workflows.whale_market_candidates")


def build_whale_market_candidates_event(
    *,
    event_type: str = POLYMARKET_WHALE_MARKETS_REQUESTED,
    source: str = "workflow.whale_market_candidates",
) -> DomainEvent:
    return DomainEvent.create(
        event_type=event_type,
        source=source,
        payload={},
        metadata={"workflow": "whale_market_candidates"},
    )


def _event_factory(event_type: str) -> Callable[[], DomainEvent]:
    def create_event() -> DomainEvent:
        return build_whale_market_candidates_event(
            event_type=event_type,
        )

    return create_event


def build_whale_market_candidates_runtime(
    *,
    bus: EventBus | None = None,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
) -> Runtime:
    runtime = Runtime(bus=bus)
    runtime.install(
        PolymarketWhaleDiscoveryBinding(),
        PolymarketWhaleMarketsBinding(min_whale_count=min_whale_count),
    )
    return runtime


async def run_whale_market_candidates(
    *,
    echo_events: bool = False,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
) -> None:
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, logger.log_domain_event)

    runtime = build_whale_market_candidates_runtime(
        bus=bus,
        min_whale_count=min_whale_count,
    )
    scheduler = Scheduler(runtime=runtime)

    scheduler.register(
        ScheduledJob(
            name="whales.discover",
            interval_seconds=3600,
            event_factory=_event_factory(POLYMARKET_WHALE_DISCOVERY_REQUESTED),
        ),
        ScheduledJob(
            name="whales.markets",
            interval_seconds=900,
            event_factory=_event_factory(POLYMARKET_WHALE_MARKETS_REQUESTED),
        ),
    )

    if echo_events:
        bus.subscribe(EventBus.WILDCARD, _print_event)

    await scheduler.run_once()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run Polymarket whale market candidate discovery.",
    )
    parser.add_argument(
        "--echo-events",
        action="store_true",
        help="Print emitted runtime events as JSON lines.",
    )
    parser.add_argument(
        "--min-whale-count",
        type=int,
        default=DEFAULT_MIN_WHALE_COUNT,
        help="Minimum matching whale count for market candidates.",
    )
    args = parser.parse_args(argv)

    asyncio.run(
        run_whale_market_candidates(
            echo_events=args.echo_events,
            min_whale_count=args.min_whale_count,
        )
    )


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
