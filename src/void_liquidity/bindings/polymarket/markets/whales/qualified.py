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
    POLYMARKET_WHALE_QUALIFIED_MARKETS_SKIPPED,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.events import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED as POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVATION_STARTED,
)
from void_liquidity.adapters.polymarket.markets.whales.candidates.repository import (
    get_latest_market_candidate_run,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.repository import (
    get_completed_qualified_market_run_for_parent,
    persist_failed_qualified_market_run,
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
DEFAULT_QUALIFIED_MARKET_PROFILES = (
    WhaleQualifiedMarketProfile(name="confirmed"),
    WhaleQualifiedMarketProfile(name="pain"),
    WhaleQualifiedMarketProfile(name="high_value"),
    WhaleQualifiedMarketProfile(name="value_per_wallet"),
)


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _profile_from_payload(payload: dict) -> WhaleQualifiedMarketProfile:
    profile_payload = payload.get("profile")

    if isinstance(profile_payload, dict):
        return WhaleQualifiedMarketProfile.model_validate(profile_payload)

    return DEFAULT_QUALIFIED_MARKET_PROFILE


def _profiles_from_payload(payload: dict) -> tuple[WhaleQualifiedMarketProfile, ...]:
    profiles_payload = payload.get("profiles")
    if isinstance(profiles_payload, list):
        return tuple(
            WhaleQualifiedMarketProfile.model_validate(profile)
            for profile in profiles_payload
            if isinstance(profile, dict)
        )

    if isinstance(payload.get("profile"), dict):
        return (_profile_from_payload(payload),)

    return DEFAULT_QUALIFIED_MARKET_PROFILES


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
            POLYMARKET_WHALE_QUALIFIED_MARKETS_SKIPPED,
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
        profiles = _profiles_from_payload(event.payload)
        limit = _limit_from_payload(event.payload)
        candidate_run_id = (
            _candidate_run_id_from_payload(event.payload)
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
            existing_run_id = get_completed_qualified_market_run_for_parent(
                candidate_run_id=candidate_run_id,
                profiles=profiles,
                limit=limit,
            )
            if existing_run_id is not None:
                await _publish(
                    bus=bus,
                    event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_SKIPPED,
                    correlation_id=event.correlation_id,
                    run_id=existing_run_id,
                    payload={
                        "profiles": [profile.name for profile in profiles],
                        "limit": limit,
                        "candidate_run_id": candidate_run_id,
                        "reason": "parent_config_already_completed",
                    },
                    metadata=metadata,
                )
                return WhaleQualifiedMarketService(profiles=profiles).list(
                    run_id=existing_run_id,
                    limit=limit,
                )

            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={
                    "profiles": [profile.name for profile in profiles],
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
                    "profiles": [profile.name for profile in profiles],
                    "limit": limit,
                    "candidate_run_id": candidate_run_id,
                },
                metadata=metadata,
            )

            service = WhaleQualifiedMarketService(profiles=profiles)
            result = service.run(candidate_run_id=candidate_run_id, limit=limit)
            service.persist(
                result=result,
                run_id=run_id,
                candidate_run_id=candidate_run_id,
                generated_at=started_at,
                limit=limit,
            )
            await _publish(
                bus=bus,
                event_type=POLYMARKET_WHALE_QUALIFIED_MARKETS_DERIVED,
                correlation_id=event.correlation_id,
                run_id=run_id,
                payload={
                    "profiles": [profile.name for profile in profiles],
                    "candidate_run_id": candidate_run_id,
                    "qualified_market_count": len(result.qualified_markets),
                    "limit": limit,
                    "max_score": _max_score(result),
                    "min_score": _min_score(result),
                },
                metadata=metadata,
            )
            completed_payload = {
                "profiles": [profile.name for profile in profiles],
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
            try:
                persist_failed_qualified_market_run(
                    profiles=profiles,
                    run_id=run_id,
                    candidate_run_id=candidate_run_id,
                    generated_at=started_at,
                    limit=limit,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            except Exception:
                pass
            failed_payload = {
                "profiles": [profile.name for profile in profiles],
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


def _max_score(result: QualifiedMarketResult) -> float | None:
    if not result.qualified_markets:
        return None

    return max(market.score for market in result.qualified_markets)


def _min_score(result: QualifiedMarketResult) -> float | None:
    if not result.qualified_markets:
        return None

    return min(market.score for market in result.qualified_markets)
