from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence, Callable


from void_liquidity.bindings.polymarket.markets.whales import (
    PolymarketWhaleMarketsBinding,
)

from void_liquidity.bindings.polymarket.discovery.whales_v2 import (
    PolymarketWhaleDiscoveryV2Binding
)

from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.runtime import Runtime
from void_liquidity.core.logging.log import VoidLogger
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)

from void_liquidity.adapters.polymarket.discovery.whales.events import (
    POLYMARKET_WHALES_V2_REQUESTED,
)

from void_liquidity.core.scheduler import Scheduler, ScheduledJob


logger = VoidLogger("void_liquidity.workflows.whale_market_candidates")


def build_whale_market_candidates_event(
    *,
    event_type: str,
    source: str = "workflow.whale_market_candidates",
) -> Callable:
    def create_event() -> DomainEvent:
        return DomainEvent.create(
            event_type=event_type,
            source=source,
            payload={},
            metadata={"workflow": "whale_market_candidates"},
        )
    return create_event



def build_whale_market_candidates_runtime(bus: EventBus | None = None) -> Runtime:
    
    runtime = Runtime(bus=bus)
    runtime.install(
        PolymarketWhaleMarketsBinding(),
        PolymarketWhaleDiscoveryV2Binding()
    )   
    return runtime


async def run_whale_market_candidates(
    *,
    echo_events: bool = False
) -> None:
    
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, logger.log_domain_event)

    runtime = build_whale_market_candidates_runtime(bus=bus)
    
    scheduler = Scheduler(runtime=runtime)
    
    scheduler.register(
        ScheduledJob(
            name="whales.discover",
            interval_seconds=3600,
            event_factory=build_whale_market_candidates_event(
                event_type=POLYMARKET_WHALES_V2_REQUESTED,   
            ),
        ),
        ScheduledJob(
            name="whales.markets",
            interval_seconds=900,
            event_factory=build_whale_market_candidates_event(
                event_type=POLYMARKET_WHALE_MARKETS_REQUESTED
            )
        )
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
    args = parser.parse_args(argv)

    asyncio.run(
        run_whale_market_candidates(
            echo_events=args.echo_events,
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
