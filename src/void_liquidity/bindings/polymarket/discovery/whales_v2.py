from __future__ import annotations

from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.discovery.whales.events import (
    POLYMARKET_WHALES_V2_COMPLETED,
    POLYMARKET_WHALES_V2_DISCOVERED,
    POLYMARKET_WHALES_V2_FAILED,
    POLYMARKET_WHALES_V2_PERSIST_COMPLETED,
    POLYMARKET_WHALES_V2_PERSIST_FAILED,
    POLYMARKET_WHALES_V2_PERSIST_STARTED,
    POLYMARKET_WHALES_V2_REQUESTED,
    POLYMARKET_WHALES_V2_STARTED,
)
from void_liquidity.adapters.polymarket.discovery.whales.profiles import (
    WhaleTrackerV2Profile,
)
from void_liquidity.adapters.polymarket.discovery.whales.tracker import WhaleTrackerV2
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.events import DomainEvent, EventBus


EVENT_SOURCE = "binding.polymarket.discovery.whales_v2"
ADAPTER_NAME = "polymarket.whales_v2"
PROVIDER_NAME = "polymarket"


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _profile_from_payload(payload: dict) -> WhaleTrackerV2Profile:
    profile_payload = payload.get("profile")

    if isinstance(profile_payload, dict):
        return WhaleTrackerV2Profile.model_validate(profile_payload)

    return WhaleTrackerV2Profile()


class PolymarketWhaleDiscoveryV2Binding:
    spec = BindingSpec(
        name="polymarket.discovery.whales_v2",
        version="1.0.0",
        description="Collects and persists Polymarket whale snapshots.",
        consumes=(POLYMARKET_WHALES_V2_REQUESTED,),
        produces=(
            POLYMARKET_WHALES_V2_STARTED,
            POLYMARKET_WHALES_V2_COMPLETED,
            POLYMARKET_WHALES_V2_FAILED,
            POLYMARKET_WHALES_V2_DISCOVERED,
            POLYMARKET_WHALES_V2_PERSIST_STARTED,
            POLYMARKET_WHALES_V2_PERSIST_COMPLETED,
            POLYMARKET_WHALES_V2_PERSIST_FAILED,
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
            tracker = WhaleTrackerV2(profile=profile)
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALES_V2_STARTED,
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
                    event_type=POLYMARKET_WHALES_V2_DISCOVERED,
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
                    event_type=POLYMARKET_WHALES_V2_PERSIST_STARTED,
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
                        event_type=POLYMARKET_WHALES_V2_PERSIST_FAILED,
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
                    event_type=POLYMARKET_WHALES_V2_PERSIST_COMPLETED,
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
                    event_type=POLYMARKET_WHALES_V2_COMPLETED,
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
                    event_type=POLYMARKET_WHALES_V2_FAILED,
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
