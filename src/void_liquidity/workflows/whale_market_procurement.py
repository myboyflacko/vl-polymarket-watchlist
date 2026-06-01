from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence

from void_liquidity.adapters.polymarket.markets.whales.candidates.service import (
    DEFAULT_MIN_WHALE_COUNT,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_COMPLETED,
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    WhaleQualifiedMarketProfile,
    WhaleQualifiedMarketProfileName,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.events import (
    POLYMARKET_WHALE_SELECTION_REQUESTED,
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
from void_liquidity.bindings.polymarket.markets.whales.selection import (
    PolymarketWhaleSelectionBinding,
)
from void_liquidity.core.cache import WorkflowCache
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.logging import VoidLogger
from void_liquidity.core.runtime import Runtime
from void_liquidity.core.scheduler import ScheduledJob, Scheduler
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_COMPLETED as POLYMARKET_WHALE_MARKET_CANDIDATES_COMPLETED,
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
    cache: WorkflowCache | None = None,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
) -> Runtime:
    runtime = Runtime(bus=bus, cache=cache)
    runtime.install(
        PolymarketWhaleDiscoveryBinding(),
        PolymarketWhaleSelectionBinding(),
        PolymarketWhaleMarketCandidatesBinding(min_whale_count=min_whale_count),
        PolymarketWhaleQualifiedMarketsBinding(),
    )
    _install_workflow_chain(runtime)
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
            name="whales.select",
            interval_seconds=3600,
            event_factory=_event_factory(build_whale_selection_event),
        ),
        ScheduledJob(
            name="whales.market_candidates",
            interval_seconds=900,
            event_factory=_event_factory(build_whale_market_candidates_event),
        ),
        ScheduledJob(
            name="whales.qualified",
            interval_seconds=900,
            event_factory=_event_factory(
                build_whale_qualified_markets_event,
                profiles=selected_qualified_profiles,
                limit=qualified_limit,
            ),
        ),
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
    selection_run_id: str | None = None,
    source: str = "workflow.whale_market_procurement",
) -> DomainEvent:
    payload = {}
    if selection_run_id is not None:
        payload["selection_run_id"] = selection_run_id

    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_MARKETS_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "whale_market_procurement"},
    )


def build_whale_selection_event(
    *,
    discovery_run_id: str | None = None,
    source: str = "workflow.whale_market_procurement",
) -> DomainEvent:
    payload = {}
    if discovery_run_id is not None:
        payload["discovery_run_id"] = discovery_run_id

    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_SELECTION_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "whale_market_procurement"},
    )


def build_whale_qualified_markets_event(
    *,
    profile: WhaleQualifiedMarketProfile | None = None,
    profiles: Sequence[WhaleQualifiedMarketProfile] | None = None,
    candidate_run_id: str | None = None,
    limit: int | None = None,
    source: str = "workflow.whale_market_procurement",
) -> DomainEvent:
    payload = {}
    if profiles is not None:
        payload["profiles"] = [item.model_dump(mode="json") for item in profiles]
    elif profile is not None:
        payload["profile"] = profile.model_dump(mode="json")
    if candidate_run_id is not None:
        payload["candidate_run_id"] = candidate_run_id
    if limit is not None:
        payload["limit"] = limit

    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "whale_market_procurement"},
    )


def _install_workflow_chain(runtime: Runtime) -> None:
    async def request_selection(event: DomainEvent) -> None:
        discovery_run_id = event.payload.get("run_id")
        if not isinstance(discovery_run_id, str):
            return

        await runtime.publish(
            build_whale_selection_event(discovery_run_id=discovery_run_id)
        )

    async def request_qualified(event: DomainEvent) -> None:
        candidate_run_id = event.payload.get("run_id")
        if not isinstance(candidate_run_id, str):
            return

        await runtime.publish(
            build_whale_qualified_markets_event(candidate_run_id=candidate_run_id)
        )

    runtime.bus.subscribe(POLYMARKET_WHALE_DISCOVERY_COMPLETED, request_selection)
    runtime.bus.subscribe(
        POLYMARKET_WHALE_MARKET_CANDIDATES_COMPLETED,
        request_qualified,
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
