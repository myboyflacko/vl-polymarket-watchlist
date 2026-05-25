from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from void_liquidity.core import DomainEvent, EventBus, Runtime
from void_liquidity.pipeline.discovery.whales import WHALE_DISCOVERY_REQUESTED
from void_liquidity.bindings.polymarket import PolymarketWhaleDiscoveryBinding
from void_liquidity.logging import VoidLogger


logger = VoidLogger("void_liquidity.workflows.track_whales")


def build_track_whales_event(
    *,
    profile_path: str | Path | None = None,
    source: str = "workflow.track_whales",
) -> DomainEvent:
    payload = {}

    if profile_path is not None:
        payload["profile_path"] = str(profile_path)

    return DomainEvent.create(
        event_type=WHALE_DISCOVERY_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "track_whales"},
    )


def build_track_whales_runtime(bus: EventBus | None = None) -> Runtime:
    runtime = Runtime(bus=bus)
    runtime.install(PolymarketWhaleDiscoveryBinding())
    return runtime


async def run_track_whales(
    *,
    profile_path: str | Path | None = None,
    echo_events: bool = False,
) -> None:
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, logger.log_domain_event)

    if echo_events:
        bus.subscribe(EventBus.WILDCARD, _print_event)

    runtime = build_track_whales_runtime(bus=bus)
    await runtime.publish(build_track_whales_event(profile_path=profile_path))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run Polymarket whale discovery.",
    )
    parser.add_argument(
        "--profile",
        help="Path to a Polymarket whale-discovery profile JSON file.",
    )
    parser.add_argument(
        "--echo-events",
        action="store_true",
        help="Print emitted runtime events as JSON lines.",
    )
    args = parser.parse_args(argv)

    asyncio.run(
        run_track_whales(
            profile_path=args.profile,
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
