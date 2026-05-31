from __future__ import annotations

from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    QualifiedMarketResult,
    WhaleQualifiedMarketProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.events import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED as POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_COMPLETED,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.events import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED as POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_FAILED,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.events import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED as POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.qualified import (
    WhaleQualifiedMarketService,
)
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.pipeline.markets.qualified import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
)


EVENT_SOURCE = "binding.polymarket.markets.whales.qualified"
ADAPTER_NAME = "polymarket.markets.whales.qualified"
PROVIDER_NAME = "polymarket"
DEFAULT_QUALIFIED_MARKET_PROFILE = WhaleQualifiedMarketProfile(name="high_value")


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _profile_from_payload(payload: dict) -> WhaleQualifiedMarketProfile:
    profile_payload = payload.get("profile")

    if isinstance(profile_payload, dict):
        return WhaleQualifiedMarketProfile.model_validate(profile_payload)

    return DEFAULT_QUALIFIED_MARKET_PROFILE


def _limit_from_payload(payload: dict) -> int | None:
    limit = payload.get("limit")

    if isinstance(limit, int):
        return limit

    return None


class PolymarketWhaleQualifiedMarketsBinding:
    spec = BindingSpec(
        name="polymarket.markets.whales.qualified",
        version="1.0.0",
        description="Qualifies Polymarket whale market candidates for strategy input.",
        consumes=(POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,),
        produces=(
            POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
            POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED,
            POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED,
            POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
            POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
            POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_COMPLETED,
            POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_FAILED,
        ),
    )

    async def handle(self, event: DomainEvent, bus: EventBus) -> QualifiedMarketResult:
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
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={"profile": profile.name, "limit": limit},
                metadata=metadata,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={"profile": profile.name, "limit": limit},
                metadata=metadata,
            )

            result = WhaleQualifiedMarketService(profile=profile).list(limit=limit)
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={
                    "profile": profile.name,
                    "qualified_market_count": len(result.qualified_markets),
                    "limit": limit,
                    "token_ids": [
                        market.candidate.token_id
                        for market in result.qualified_markets
                    ],
                },
                metadata=metadata,
            )
            completed_payload = {
                "profile": profile.name,
                "qualified_market_count": len(result.qualified_markets),
                "limit": limit,
            }
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_COMPLETED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload=completed_payload,
                metadata=metadata,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED,
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
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_FAILED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload=failed_payload,
                metadata=metadata,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED,
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
