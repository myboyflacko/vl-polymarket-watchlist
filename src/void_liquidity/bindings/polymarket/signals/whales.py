from __future__ import annotations

from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.signals.whales.domain import (
    MarketSignalResult,
    WhaleSignalProfile,
)
from void_liquidity.adapters.polymarket.signals.whales.events import (
    POLYMARKET_WHALE_SIGNALS_COMPLETED as POLYMARKET_WHALE_SIGNALS_DERIVATION_COMPLETED,
)
from void_liquidity.adapters.polymarket.signals.whales.events import (
    POLYMARKET_WHALE_SIGNALS_DERIVED,
    POLYMARKET_WHALE_SIGNALS_FAILED as POLYMARKET_WHALE_SIGNALS_DERIVATION_FAILED,
)
from void_liquidity.adapters.polymarket.signals.whales.events import (
    POLYMARKET_WHALE_SIGNALS_STARTED as POLYMARKET_WHALE_SIGNALS_DERIVATION_STARTED,
)
from void_liquidity.adapters.polymarket.signals.whales.signals import (
    WhaleSignalService,
)
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.pipeline.signals.whales import (
    POLYMARKET_WHALE_SIGNALS_COMPLETED,
    POLYMARKET_WHALE_SIGNALS_FAILED,
    POLYMARKET_WHALE_SIGNALS_REQUESTED,
    POLYMARKET_WHALE_SIGNALS_STARTED,
)


EVENT_SOURCE = "binding.polymarket.signals.whales"
ADAPTER_NAME = "polymarket.signals.whales"
PROVIDER_NAME = "polymarket"
DEFAULT_SIGNAL_PROFILE = WhaleSignalProfile(name="high_value")


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _profile_from_payload(payload: dict) -> WhaleSignalProfile:
    profile_payload = payload.get("profile")

    if isinstance(profile_payload, dict):
        return WhaleSignalProfile.model_validate(profile_payload)

    return DEFAULT_SIGNAL_PROFILE


def _limit_from_payload(payload: dict) -> int | None:
    limit = payload.get("limit")

    if isinstance(limit, int):
        return limit

    return None


class PolymarketWhaleSignalsBinding:
    spec = BindingSpec(
        name="polymarket.signals.whales",
        version="1.0.0",
        description="Derives Polymarket whale market signals from latest market candidates.",
        consumes=(POLYMARKET_WHALE_SIGNALS_REQUESTED,),
        produces=(
            POLYMARKET_WHALE_SIGNALS_STARTED,
            POLYMARKET_WHALE_SIGNALS_COMPLETED,
            POLYMARKET_WHALE_SIGNALS_FAILED,
            POLYMARKET_WHALE_SIGNALS_DERIVATION_STARTED,
            POLYMARKET_WHALE_SIGNALS_DERIVED,
            POLYMARKET_WHALE_SIGNALS_DERIVATION_COMPLETED,
            POLYMARKET_WHALE_SIGNALS_DERIVATION_FAILED,
        ),
    )

    async def handle(self, event: DomainEvent, bus: EventBus) -> MarketSignalResult:
        started_at = datetime.now(UTC)
        run_id = _build_run_id(started_at)
        profile = _profile_from_payload(event.payload)
        limit = _limit_from_payload(event.payload)
        metadata = {
            "workflow": event.metadata.get("workflow"),
            "adapter": ADAPTER_NAME,
            "provider": PROVIDER_NAME,
        }

        try:
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_SIGNALS_STARTED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={"profile": profile.name, "limit": limit},
                metadata=metadata,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_SIGNALS_DERIVATION_STARTED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={"profile": profile.name, "limit": limit},
                metadata=metadata,
            )

            result = WhaleSignalService(profile=profile).list(limit=limit)
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_SIGNALS_DERIVED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={
                    "profile": profile.name,
                    "signal_count": len(result.signals),
                    "limit": limit,
                    "token_ids": [
                        signal.candidate.token_id for signal in result.signals
                    ],
                },
                metadata=metadata,
            )
            completed_payload = {
                "profile": profile.name,
                "signal_count": len(result.signals),
                "limit": limit,
            }
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_SIGNALS_DERIVATION_COMPLETED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload=completed_payload,
                metadata=metadata,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_SIGNALS_COMPLETED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload=completed_payload,
                metadata=metadata,
            )
            return result
        except Exception as exc:
            failed_payload = {
                "profile": profile.name,
                "limit": limit,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_SIGNALS_DERIVATION_FAILED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload=failed_payload,
                metadata=metadata,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_SIGNALS_FAILED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload=failed_payload,
                metadata=metadata,
            )
            raise


async def _publish(
    *,
    bus: EventBus,
    event_type: str,
    correlation_id: str,
    run_id: str,
    payload: dict,
    metadata: dict,
) -> None:
    await bus.publish(
        DomainEvent.create(
            event_type=event_type,
            source=EVENT_SOURCE,
            correlation_id=correlation_id,
            payload={"run_id": run_id, **payload},
            metadata=metadata,
        )
    )
