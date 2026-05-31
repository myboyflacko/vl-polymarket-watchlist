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
from void_liquidity.adapters.polymarket.signals.whales.domain import (
    WhaleSignalProfile,
    WhaleSignalProfileName,
)
from void_liquidity.bindings.polymarket.markets.whales.candidates import (
    PolymarketWhaleMarketCandidatesBinding,
)
from void_liquidity.bindings.polymarket.markets.whales.discovery import (
    PolymarketWhaleDiscoveryBinding,
)
from void_liquidity.bindings.polymarket.signals.whales import (
    PolymarketWhaleSignalsBinding,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.logging import VoidLogger
from void_liquidity.core.runtime import Runtime
from void_liquidity.core.scheduler import ScheduledJob, Scheduler
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_REQUESTED,
)
from void_liquidity.pipeline.signals.whales import (
    POLYMARKET_WHALE_SIGNALS_REQUESTED,
)


DEFAULT_SIGNAL_PROFILE_NAMES: tuple[WhaleSignalProfileName, ...] = (
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
        PolymarketWhaleSignalsBinding(),
    )
    return runtime


def build_whale_market_procurement_scheduler(
    *,
    runtime: Runtime,
    discovery_profile: WhaleDiscoveryProfile | None = None,
    signal_profiles: Sequence[WhaleSignalProfile] | None = None,
    signal_limit: int | None = None,
) -> Scheduler:
    scheduler = Scheduler(runtime=runtime)
    selected_signal_profiles = signal_profiles or _default_signal_profiles()

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
                name=f"whales.signals.{profile.name}",
                interval_seconds=900,
                event_factory=_event_factory(
                    build_whale_signals_event,
                    profile=profile,
                    limit=signal_limit,
                ),
            )
            for profile in selected_signal_profiles
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


def build_whale_signals_event(
    *,
    profile: WhaleSignalProfile,
    limit: int | None = None,
    source: str = "workflow.whale_market_procurement",
) -> DomainEvent:
    payload = {"profile": profile.model_dump(mode="json")}
    if limit is not None:
        payload["limit"] = limit

    return DomainEvent.create(
        event_type=POLYMARKET_WHALE_SIGNALS_REQUESTED,
        source=source,
        payload=payload,
        metadata={"workflow": "whale_market_procurement"},
    )


async def run_whale_market_procurement(
    *,
    discovery_profile: WhaleDiscoveryProfile | None = None,
    echo_events: bool = False,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
    signal_profiles: Sequence[WhaleSignalProfile] | None = None,
    signal_limit: int | None = None,
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
        signal_profiles=signal_profiles,
        signal_limit=signal_limit,
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
        "--signal-profile",
        choices=DEFAULT_SIGNAL_PROFILE_NAMES,
        action="append",
        help="Signal profile to derive. Repeat to select multiple profiles.",
    )
    parser.add_argument(
        "--signal-limit",
        type=int,
        default=None,
        help="Maximum signals per selected profile.",
    )
    args = parser.parse_args(argv)

    asyncio.run(
        run_whale_market_procurement(
            discovery_profile=_discovery_profile_from_args(args),
            echo_events=args.echo_events,
            min_whale_count=args.min_whale_count,
            signal_profiles=_signal_profiles_from_args(args),
            signal_limit=args.signal_limit,
        )
    )


def _event_factory(factory: Callable[..., DomainEvent], **kwargs):
    def create_event() -> DomainEvent:
        return factory(**kwargs)

    return create_event


def _default_signal_profiles() -> tuple[WhaleSignalProfile, ...]:
    return tuple(
        WhaleSignalProfile(name=name)
        for name in DEFAULT_SIGNAL_PROFILE_NAMES
    )


def _discovery_profile_from_args(
    args: argparse.Namespace,
) -> WhaleDiscoveryProfile | None:
    if args.wallet_count is None:
        return None

    return WhaleDiscoveryProfile(wallet_count=args.wallet_count)


def _signal_profiles_from_args(
    args: argparse.Namespace,
) -> tuple[WhaleSignalProfile, ...] | None:
    if not args.signal_profile:
        return None

    return tuple(
        WhaleSignalProfile(name=name)
        for name in args.signal_profile
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
