from __future__ import annotations

from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales.discovery.events import (
    POLYMARKET_WHALE_DISCOVERY_COMPLETED,
    POLYMARKET_WHALE_DISCOVERY_DISCOVERED,
    POLYMARKET_WHALE_DISCOVERY_FAILED,
    POLYMARKET_WHALE_DISCOVERY_PERSIST_COMPLETED,
    POLYMARKET_WHALE_DISCOVERY_PERSIST_FAILED,
    POLYMARKET_WHALE_DISCOVERY_PERSIST_STARTED,
    POLYMARKET_WHALE_DISCOVERY_REQUESTED,
    POLYMARKET_WHALE_DISCOVERY_STARTED,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.tracker import (
    WhaleDiscoveryService,
)
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.events import DomainEvent, EventBus


EVENT_SOURCE = "binding.polymarket.markets.whales.discovery"
ADAPTER_NAME = "polymarket.markets.whales.discovery"
PROVIDER_NAME = "polymarket"


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _profile_from_payload(payload: dict) -> WhaleDiscoveryProfile:
    profile_payload = payload.get("profile")

    if isinstance(profile_payload, dict):
        return WhaleDiscoveryProfile.model_validate(profile_payload)

    return WhaleDiscoveryProfile()


class PolymarketWhaleDiscoveryBinding:
    spec = BindingSpec(
        name="polymarket.markets.whales.discovery",
        version="1.0.0",
        description="Collects and persists Polymarket whale snapshots.",
        consumes=(POLYMARKET_WHALE_DISCOVERY_REQUESTED,),
        produces=(
            POLYMARKET_WHALE_DISCOVERY_STARTED,
            POLYMARKET_WHALE_DISCOVERY_COMPLETED,
            POLYMARKET_WHALE_DISCOVERY_FAILED,
            POLYMARKET_WHALE_DISCOVERY_DISCOVERED,
            POLYMARKET_WHALE_DISCOVERY_PERSIST_STARTED,
            POLYMARKET_WHALE_DISCOVERY_PERSIST_COMPLETED,
            POLYMARKET_WHALE_DISCOVERY_PERSIST_FAILED,
        ),
    )

    async def handle(self, event: DomainEvent, bus: EventBus) -> None:
        started_at = datetime.now(UTC)
        run_id = _build_run_id(started_at)
        metadata = {
            "workflow": event.metadata.get("workflow"),
            "adapter": ADAPTER_NAME,
            "provider": PROVIDER_NAME,
        }

        try:
            profile = _profile_from_payload(event.payload)
            tracker = WhaleDiscoveryService(profile=profile)
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_DISCOVERY_STARTED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "profile_version": profile.profile_version,
                        "wallet_count": profile.wallet_count,
                    },
                    metadata=metadata,
                )
            )

            whales = await tracker.run(now=started_at)
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_DISCOVERY_DISCOVERED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "wallets": whales.proxy_wallets(),
                        "collected_wallet_count": whales.wallet_count,
                        "candidate_wallet_count": whales.candidate_wallet_count,
                        "checked_wallet_count": whales.checked_wallet_count,
                        "successful_wallet_count": whales.successful_wallet_count,
                        "failed_wallet_count": whales.failed_wallet_count,
                        "partial": whales.partial,
                        "collection_error_count": len(whales.collection_errors),
                    },
                    metadata=metadata,
                )
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_DISCOVERY_PERSIST_STARTED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "collected_wallet_count": whales.wallet_count,
                    },
                    metadata=metadata,
                )
            )
            try:
                tracker.persist(
                    whales=whales,
                    run_id=run_id,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
            except Exception as exc:
                await bus.publish(
                    DomainEvent.create(
                        event_type=POLYMARKET_WHALE_DISCOVERY_PERSIST_FAILED,
                        source=EVENT_SOURCE,
                        correlation_id=event.correlation_id,
                        payload={
                            "run_id": run_id,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                        metadata=metadata,
                    )
                )
                raise

            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_DISCOVERY_PERSIST_COMPLETED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "collected_wallet_count": whales.wallet_count,
                    },
                    metadata=metadata,
                )
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_DISCOVERY_COMPLETED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "candidate_wallet_count": whales.candidate_wallet_count,
                        "checked_wallet_count": whales.checked_wallet_count,
                        "collected_wallet_count": whales.wallet_count,
                        "successful_wallet_count": whales.successful_wallet_count,
                        "failed_wallet_count": whales.failed_wallet_count,
                        "partial": whales.partial,
                        "collection_error_count": len(whales.collection_errors),
                    },
                    metadata=metadata,
                )
            )
        except Exception as exc:
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_DISCOVERY_FAILED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    metadata=metadata,
                )
            )
            raise
