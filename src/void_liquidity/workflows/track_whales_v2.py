from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence

from void_liquidity.adapters.polymarket.discovery.whales.events import (
    POLYMARKET_WHALES_V2_REQUESTED,
)
from void_liquidity.adapters.polymarket.discovery.whales.profiles import (
    WhaleTrackerV2Profile,
)
from void_liquidity.bindings.polymarket.discovery.whales_v2 import (
    PolymarketWhaleDiscoveryV2Binding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.runtime import Runtime
from void_liquidity.logging.log import VoidLogger


logger = VoidLogger("void_liquidity.workflows.track_whales_v2")


def build_track_whales_v2_event(
    *,
    profile: WhaleTrackerV2Profile | None = None,
    source: str = "workflow.track_whales_v2",
) -> DomainEvent:
    payload = {}

    if profile is not None:
        payload["profile"] = profile.model_dump(mode="json")

    return DomainEvent.create(
        event_type=POLYMARKET_WHALES_V2_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "track_whales_v2"},
    )


def build_track_whales_v2_runtime(bus: EventBus | None = None) -> Runtime:
    runtime = Runtime(bus=bus)
    runtime.install(PolymarketWhaleDiscoveryV2Binding())
    return runtime


async def run_track_whales_v2(
    *,
    profile: WhaleTrackerV2Profile | None = None,
    echo_events: bool = False,
) -> None:
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, logger.log_domain_event)

    if echo_events:
        bus.subscribe(EventBus.WILDCARD, _print_event)

    runtime = build_track_whales_v2_runtime(bus=bus)
    await runtime.publish(build_track_whales_v2_event(profile=profile))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run Polymarket whale discovery V2.",
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
    asyncio.run(run_track_whales_v2(profile=profile, echo_events=args.echo_events))


def _build_profile_from_args(args: argparse.Namespace) -> WhaleTrackerV2Profile | None:
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

    return WhaleTrackerV2Profile(**profile_payload)


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
