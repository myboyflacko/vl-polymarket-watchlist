from __future__ import annotations

from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales.selection.events import (
    POLYMARKET_WHALE_SELECTION_COMPLETED,
    POLYMARKET_WHALE_SELECTION_FAILED,
    POLYMARKET_WHALE_SELECTION_REQUESTED,
    POLYMARKET_WHALE_SELECTION_SELECTED,
    POLYMARKET_WHALE_SELECTION_STARTED,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
    get_latest_discovery_run_id,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.profiles import (
    WhaleSelectionProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.ranking import (
    WhaleSelectionRankingResult,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.service import (
    WhaleSelectionService,
)
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.cache import WorkflowCache
from void_liquidity.core.events import DomainEvent, EventBus


EVENT_SOURCE = "binding.polymarket.markets.whales.selection"
ADAPTER_NAME = "polymarket.markets.whales.selection"
PROVIDER_NAME = "polymarket"
CACHE_NAMESPACE = "polymarket.markets.whales.selection"


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _profile_from_payload(payload: dict) -> WhaleSelectionProfile | None:
    profile_payload = payload.get("profile")

    if isinstance(profile_payload, dict):
        return WhaleSelectionProfile.model_validate(profile_payload)

    return None


def _discovery_run_id_from_payload(payload: dict) -> str | None:
    discovery_run_id = payload.get("discovery_run_id")
    if isinstance(discovery_run_id, str):
        return discovery_run_id

    return None


class PolymarketWhaleSelectionBinding:
    spec = BindingSpec(
        name="polymarket.markets.whales.selection",
        version="1.0.0",
        description="Ranks persisted Polymarket whales for downstream market analysis.",
        consumes=(POLYMARKET_WHALE_SELECTION_REQUESTED,),
        produces=(
            POLYMARKET_WHALE_SELECTION_STARTED,
            POLYMARKET_WHALE_SELECTION_SELECTED,
            POLYMARKET_WHALE_SELECTION_COMPLETED,
            POLYMARKET_WHALE_SELECTION_FAILED,
        ),
    )

    async def handle(
        self,
        event: DomainEvent,
        bus: EventBus,
        cache: WorkflowCache | None = None,
    ) -> WhaleSelectionRankingResult:
        started_at = datetime.now(UTC)
        run_id = _build_run_id(started_at)
        discovery_run_id = (
            _discovery_run_id_from_payload(event.payload)
            or (
                cache.get("polymarket.markets.whales.discovery", "latest_run_id")
                if cache is not None
                else None
            )
            or get_latest_discovery_run_id()
        )
        if discovery_run_id is None:
            raise ValueError("discovery_run_id is required without discovery runs")
        metadata = {
            "workflow": event.metadata.get("workflow"),
            "adapter": ADAPTER_NAME,
            "provider": PROVIDER_NAME,
        }

        try:
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_SELECTION_STARTED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "discovery_run_id": discovery_run_id,
                    },
                    metadata=metadata,
                )
            )

            service = WhaleSelectionService(profile=_profile_from_payload(event.payload))
            result = service.run(discovery_run_id=discovery_run_id)
            service.persist(
                ranking=result,
                run_id=run_id,
                discovery_run_id=discovery_run_id,
                generated_at=started_at,
            )
            if cache is not None:
                cache.set(CACHE_NAMESPACE, "latest_run_id", run_id)
                cache.set(CACHE_NAMESPACE, "latest", result)
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_SELECTION_SELECTED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "discovery_run_id": discovery_run_id,
                        "ranking_method": result.method,
                        "ranked_wallet_count": len(result.ranked_whales),
                        "removed_wallet_count": len(result.removed_whales),
                        "ranked_wallets": [
                            ranked.whale.proxy_wallet
                            for ranked in result.ranked_whales
                        ],
                        "removed_wallets": result.removed_wallets,
                    },
                    metadata=metadata,
                )
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_SELECTION_COMPLETED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "discovery_run_id": discovery_run_id,
                        "ranking_method": result.method,
                        "ranked_wallet_count": len(result.ranked_whales),
                        "removed_wallet_count": len(result.removed_whales),
                    },
                    metadata=metadata,
                )
            )
            return result
        except Exception as exc:
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_SELECTION_FAILED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "discovery_run_id": discovery_run_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    metadata=metadata,
                )
            )
            raise
