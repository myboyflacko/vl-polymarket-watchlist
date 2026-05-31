from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence

from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.bindings.polymarket.markets.whales.discovery import (
    PolymarketWhaleDiscoveryBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.runtime import Runtime
from void_liquidity.logging.log import VoidLogger


logger = VoidLogger("void_liquidity.workflows.whale_discovery")


def build_whale_discovery_event(
    *,
    profile: WhaleDiscoveryProfile | None = None,
    source: str = "workflow.whale_discovery",
) -> DomainEvent:
    payload = {}

    if profile is not None:
        payload["profile"] = profile.model_dump(mode="json")

    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_DISCOVERY_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "whale_discovery"},
    )


def build_whale_discovery_runtime(bus: EventBus | None = None) -> Runtime:
    runtime = Runtime(bus=bus)
    runtime.install(PolymarketWhaleDiscoveryBinding())
    return runtime


async def run_whale_discovery(
    *,
    profile: WhaleDiscoveryProfile | None = None,
    echo_events: bool = False,
) -> None:
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, logger.log_domain_event)

    if echo_events:
        bus.subscribe(EventBus.WILDCARD, _print_event)

    runtime = build_whale_discovery_runtime(bus=bus)
    await runtime.publish(build_whale_discovery_event(profile=profile))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run Polymarket whale discovery.",
    )
    parser.add_argument(
        "--wallet-count",
        type=int,
        default=None,
        help="Number of PnL and volume leaderboard wallets to collect.",
    )
    parser.add_argument(
        "--trade-window-days",
        type=int,
        default=None,
        help="Trade activity window in days.",
    )
    parser.add_argument(
        "--recent-window-days",
        type=int,
        default=None,
        help="Recent activity window in days.",
    )
    parser.add_argument(
        "--echo-events",
        action="store_true",
        help="Print emitted runtime events as JSON lines.",
    )
    args = parser.parse_args(argv)

    profile = _build_profile_from_args(args)
    asyncio.run(run_whale_discovery(profile=profile, echo_events=args.echo_events))


def _build_profile_from_args(args: argparse.Namespace) -> WhaleDiscoveryProfile | None:
    profile_overrides = {
        "wallet_count": args.wallet_count,
        "trade_window_days": args.trade_window_days,
        "recent_window_days": args.recent_window_days,
    }
    profile_payload = {
        key: value for key, value in profile_overrides.items() if value is not None
    }

    if not profile_payload:
        return None

    return WhaleDiscoveryProfile(**profile_payload)


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
