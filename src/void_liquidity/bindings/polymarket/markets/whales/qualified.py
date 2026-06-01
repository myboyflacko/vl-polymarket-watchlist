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
from void_liquidity.adapters.polymarket.markets.whales.candidates.repository import (
    get_latest_market_candidate_run,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.service import (
    WhaleQualifiedMarketService,
)
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.cache import WorkflowCache
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
CACHE_NAMESPACE = "polymarket.markets.whales.qualified"


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


def _candidate_run_id_from_payload(payload: dict) -> str | None:
    candidate_run_id = payload.get("candidate_run_id")
    if isinstance(candidate_run_id, str):
        return candidate_run_id

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

    async def handle(
        self,
        event: DomainEvent,
        bus: EventBus,
        cache: WorkflowCache | None = None,
    ) -> QualifiedMarketResult:
        started_at = datetime.now(UTC)
        run_id = _build_run_id(started_at)
        profile = _profile_from_payload(event.payload)
        limit = _limit_from_payload(event.payload)
        candidate_run_id = (
            _candidate_run_id_from_payload(event.payload)
            or (
                cache.get("polymarket.markets.whales.candidates", "latest_run_id")
                if cache is not None
                else None
            )
            or (
                latest_run.run_id
                if (latest_run := get_latest_market_candidate_run()) is not None
                else None
            )
        )
        if candidate_run_id is None:
            raise ValueError("candidate_run_id is required without candidate runs")
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
                payload={
                    "profile": profile.name,
                    "limit": limit,
                    "candidate_run_id": candidate_run_id,
                },
                metadata=metadata,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={
                    "profile": profile.name,
                    "limit": limit,
                    "candidate_run_id": candidate_run_id,
                },
                metadata=metadata,
            )

            service = WhaleQualifiedMarketService(profile=profile)
            result = service.run(candidate_run_id=candidate_run_id, limit=limit)
            service.persist(
                result=result,
                run_id=run_id,
                candidate_run_id=candidate_run_id,
                generated_at=started_at,
                limit=limit,
            )
            if cache is not None:
                cache.set(CACHE_NAMESPACE, "latest_run_id", run_id)
                cache.set(CACHE_NAMESPACE, "latest", result)
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={
                    "profile": profile.name,
                    "candidate_run_id": candidate_run_id,
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
                "candidate_run_id": candidate_run_id,
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
                "candidate_run_id": candidate_run_id,
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
