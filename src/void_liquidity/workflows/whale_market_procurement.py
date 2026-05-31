from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence

from void_liquidity.adapters.polymarket.markets.whales.candidates.collector import (
    DEFAULT_MIN_WHALE_COUNT,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    WhaleQualifiedMarketProfile,
    WhaleQualifiedMarketProfileName,
)
from void_liquidity.bindings.polymarket.markets.whales.candidates import (
    PolymarketWhaleMarketCandidatesBinding,
)
from void_liquidity.bindings.polymarket.markets.whales.discovery import (
    PolymarketWhaleDiscoveryBinding,
)
from void_liquidity.bindings.polymarket.markets.whales.qualified import (
    PolymarketWhaleQualifiedMarketsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.logging import VoidLogger
from void_liquidity.core.runtime import Runtime
from void_liquidity.core.scheduler import ScheduledJob, Scheduler
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)
from void_liquidity.pipeline.markets.qualified import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,
)


DEFAULT_QUALIFIED_PROFILE_NAMES: tuple[WhaleQualifiedMarketProfileName, ...] = (
    "confirmed",
    "pain",
    "high_value",
    "value_per_wallet",
)

logger = VoidLogger("void_liquidity.workflows.whale_market_procurement")


def build_whale_market_procurement_runtime(
    *,
    bus: EventBus | None = None,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
) -> Runtime:
    runtime = Runtime(bus=bus)
    runtime.install(
        PolymarketWhaleDiscoveryBinding(),
        PolymarketWhaleMarketCandidatesBinding(min_whale_count=min_whale_count),
        PolymarketWhaleQualifiedMarketsBinding(),
    )
    return runtime


def build_whale_market_procurement_scheduler(
    *,
    runtime: Runtime,
    discovery_profile: WhaleDiscoveryProfile | None = None,
    qualified_profiles: Sequence[WhaleQualifiedMarketProfile] | None = None,
    qualified_limit: int | None = None,
) -> Scheduler:
    scheduler = Scheduler(runtime=runtime)
    selected_qualified_profiles = qualified_profiles or _default_qualified_profiles()

    scheduler.register(
        ScheduledJob(
            name="whales.discover",
            interval_seconds=3600,
            event_factory=_event_factory(
                build_whale_discovery_event,
                profile=discovery_profile,
            ),
        ),
        ScheduledJob(
            name="whales.market_candidates",
            interval_seconds=900,
            event_factory=_event_factory(build_whale_market_candidates_event),
        ),
        *[
            ScheduledJob(
                name=f"whales.qualified.{profile.name}",
                interval_seconds=900,
                event_factory=_event_factory(
                    build_whale_qualified_markets_event,
                    profile=profile,
                    limit=qualified_limit,
                ),
            )
            for profile in selected_qualified_profiles
        ],
    )
    return scheduler


def build_whale_discovery_event(
    *,
    profile: WhaleDiscoveryProfile | None = None,
    source: str = "workflow.whale_market_procurement",
) -> DomainEvent:
    payload = {}
    if profile is not None:
        payload["profile"] = profile.model_dump(mode="json")

    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_DISCOVERY_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "whale_market_procurement"},
    )


def build_whale_market_candidates_event(
    *,
    source: str = "workflow.whale_market_procurement",
) -> DomainEvent:
    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_MARKETS_REQUESTED,
        source=source,
        payload={},
        metadata={"workflow": "whale_market_procurement"},
    )


def build_whale_qualified_markets_event(
    *,
    profile: WhaleQualifiedMarketProfile,
    limit: int | None = None,
    source: str = "workflow.whale_market_procurement",
) -> DomainEvent:
    payload = {"profile": profile.model_dump(mode="json")}
    if limit is not None:
        payload["limit"] = limit

    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "whale_market_procurement"},
    )


async def run_whale_market_procurement(
    *,
    discovery_profile: WhaleDiscoveryProfile | None = None,
    echo_events: bool = False,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    qualified_profiles: Sequence[WhaleQualifiedMarketProfile] | None = None,
    qualified_limit: int | None = None,
) -> None:
    bus = EventBus()
    bus.subscribe(EventBus.WILDCARD, logger.log_domain_event)

    if echo_events:
        bus.subscribe(EventBus.WILDCARD, _print_event)

    runtime = build_whale_market_procurement_runtime(
        bus=bus,
        min_whale_count=min_whale_count,
    )
    scheduler = build_whale_market_procurement_scheduler(
        runtime=runtime,
        discovery_profile=discovery_profile,
        qualified_profiles=qualified_profiles,
        qualified_limit=qualified_limit,
    )
    await scheduler.run_once()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the full Polymarket whale market procurement workflow.",
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
    parser.add_argument(
        "--wallet-count",
        type=int,
        default=None,
        help="Number of PnL and volume leaderboard wallets to collect.",
    )
    parser.add_argument(
        "--qualified-profile",
        choices=DEFAULT_QUALIFIED_PROFILE_NAMES,
        action="append",
        help="Qualified market profile to apply. Repeat to select multiple profiles.",
    )
    parser.add_argument(
        "--qualified-limit",
        type=int,
        default=None,
        help="Maximum qualified markets per selected profile.",
    )
    args = parser.parse_args(argv)

    asyncio.run(
        run_whale_market_procurement(
            discovery_profile=_discovery_profile_from_args(args),
            echo_events=args.echo_events,
            min_whale_count=args.min_whale_count,
            qualified_profiles=_qualified_profiles_from_args(args),
            qualified_limit=args.qualified_limit,
        )
    )


def _event_factory(factory: Callable[..., DomainEvent], **kwargs):
    def create_event() -> DomainEvent:
        return factory(**kwargs)

    return create_event


def _default_qualified_profiles() -> tuple[WhaleQualifiedMarketProfile, ...]:
    return tuple(
        WhaleQualifiedMarketProfile(name=name)
        for name in DEFAULT_QUALIFIED_PROFILE_NAMES
    )


def _discovery_profile_from_args(
    args: argparse.Namespace,
) -> WhaleDiscoveryProfile | None:
    if args.wallet_count is None:
        return None

    return WhaleDiscoveryProfile(wallet_count=args.wallet_count)


def _qualified_profiles_from_args(
    args: argparse.Namespace,
) -> tuple[WhaleQualifiedMarketProfile, ...] | None:
    if not args.qualified_profile:
        return None

    return tuple(
        WhaleQualifiedMarketProfile(name=name)
        for name in args.qualified_profile
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
