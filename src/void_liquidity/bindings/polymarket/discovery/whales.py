from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from void_liquidity.adapters.polymarket.discovery.whales import (
    WhaleTracker,
    load_workflow_profile,
)
from void_liquidity.adapters.polymarket.discovery.whales.events import (
    POLYMARKET_WHALES_DISCOVERED,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.pipeline.discovery.whales.events import (
    WHALE_DISCOVERY_COMPLETED,
    WHALE_DISCOVERY_FAILED,
    WHALE_DISCOVERY_REQUESTED,
    WHALE_DISCOVERY_STARTED,
)


EVENT_SOURCE = "binding.polymarket.discovery.whales"
ADAPTER_NAME = "polymarket.whales"
PROVIDER_NAME = "polymarket"


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


class PolymarketWhaleDiscoveryBinding:
    spec = BindingSpec(
        name="polymarket.discovery.whales",
        version="1.0.0",
        description="Collects qualified Polymarket whales and persists snapshots.",
        consumes=(WHALE_DISCOVERY_REQUESTED,),
        produces=(
            WHALE_DISCOVERY_STARTED,
            WHALE_DISCOVERY_COMPLETED,
            WHALE_DISCOVERY_FAILED,
            POLYMARKET_WHALES_DISCOVERED,
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

        profile_path = event.payload.get("profile_path")
        try:
            profile = (
                load_workflow_profile(Path(profile_path))
                if isinstance(profile_path, str)
                else load_workflow_profile()
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=WHALE_DISCOVERY_STARTED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "profile_version": profile.profile_version,
                        "target_wallet_count": profile.target_wallet_count,
                    },
                    metadata=metadata,
                )
            )

            result = await WhaleTracker(profile=profile).run(
                run_id=run_id,
                started_at=started_at,
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=WHALE_DISCOVERY_COMPLETED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "candidate_wallet_count": result.candidate_wallet_count,
                        "checked_wallet_count": result.checked_wallet_count,
                        "accepted_wallet_count": result.accepted_wallet_count,
                        "request_error_count": len(result.request_errors),
                    },
                    metadata=metadata,
                )
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALES_DISCOVERED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "wallets": list(result.whales),
                        "accepted_wallet_count": result.accepted_wallet_count,
                        "checked_wallet_count": result.checked_wallet_count,
                    },
                    metadata=metadata,
                )
            )
        except Exception as exc:
            await bus.publish(
                DomainEvent.create(
                    event_type=WHALE_DISCOVERY_FAILED,
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
