from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales.candidates.service import (
    DEFAULT_MIN_WHALE_COUNT,
    WhaleMarketCandidateService,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.repository import (
    get_latest_selection_run_id,
)
from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import (
    WhaleMarketCandidates,
)
from void_liquidity.adapters.polymarket.markets.whales.candidates.events import (
    POLYMARKET_WHALE_MARKETS_DISCOVERED,
    POLYMARKET_WHALE_MARKETS_PERSIST_COMPLETED,
    POLYMARKET_WHALE_MARKETS_PERSIST_FAILED,
    POLYMARKET_WHALE_MARKETS_PERSIST_STARTED,
)
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.cache import WorkflowCache
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.pipeline.markets.whales import (
    POLYMARKET_WHALE_MARKETS_COMPLETED,
    POLYMARKET_WHALE_MARKETS_FAILED,
    POLYMARKET_WHALE_MARKETS_REQUESTED,
    POLYMARKET_WHALE_MARKETS_STARTED,
)


EVENT_SOURCE = "binding.polymarket.markets.whales.candidates"
ADAPTER_NAME = "polymarket.markets.whales.candidates"
PROVIDER_NAME = "polymarket"
CACHE_NAMESPACE = "polymarket.markets.whales.candidates"


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _selection_run_id_from_payload(payload: dict) -> str | None:
    selection_run_id = payload.get("selection_run_id")
    if isinstance(selection_run_id, str):
        return selection_run_id

    return None


class PolymarketWhaleMarketCandidatesBinding:
    spec = BindingSpec(
        name="polymarket.markets.whales.candidates",
        version="1.0.0",
        description="Collects open whale positions and groups them into market candidates.",
        consumes=(POLYMARKET_WHALE_MARKETS_REQUESTED,),
        produces=(
            POLYMARKET_WHALE_MARKETS_STARTED,
            POLYMARKET_WHALE_MARKETS_COMPLETED,
            POLYMARKET_WHALE_MARKETS_FAILED,
            POLYMARKET_WHALE_MARKETS_DISCOVERED,
            POLYMARKET_WHALE_MARKETS_PERSIST_STARTED,
            POLYMARKET_WHALE_MARKETS_PERSIST_COMPLETED,
            POLYMARKET_WHALE_MARKETS_PERSIST_FAILED,
        ),
    )

    def __init__(self, *, min_whale_count: int = DEFAULT_MIN_WHALE_COUNT) -> None:
        self.min_whale_count = min_whale_count

    async def handle(
        self,
        event: DomainEvent,
        bus: EventBus,
        cache: WorkflowCache | None = None,
    ) -> WhaleMarketCandidates:
        started_at = datetime.now(UTC)
        run_id = _build_run_id(started_at)
        selection_run_id = (
            _selection_run_id_from_payload(event.payload)
            or (
                cache.get("polymarket.markets.whales.selection", "latest_run_id")
                if cache is not None
                else None
            )
            or get_latest_selection_run_id()
        )
        if selection_run_id is None:
            raise ValueError("selection_run_id is required without selection runs")
        metadata = {
            "workflow": event.metadata.get("workflow"),
            "adapter": ADAPTER_NAME,
            "provider": PROVIDER_NAME,
        }

        try:
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_STARTED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "selection_run_id": selection_run_id,
                    },
                    metadata=metadata,
                )
            )

            service = WhaleMarketCandidateService(min_whale_count=self.min_whale_count)
            result = await service.run(selection_run_id=selection_run_id)
            if cache is not None:
                cache.set(CACHE_NAMESPACE, "latest", result)
                cache.set(CACHE_NAMESPACE, "latest_run_id", run_id)

            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_DISCOVERED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "selection_run_id": selection_run_id,
                        "candidate_count": len(result.candidates),
                        "position_count": len(result.positions),
                        "error_count": len(result.errors),
                        "min_whale_count": self.min_whale_count,
                        "error_summary": _error_summary(result.errors),
                    },
                    metadata=metadata,
                )
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_PERSIST_STARTED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "selection_run_id": selection_run_id,
                        "candidate_count": len(result.candidates),
                        "position_count": len(result.positions),
                        "error_count": len(result.errors),
                        "min_whale_count": self.min_whale_count,
                    },
                    metadata=metadata,
                )
            )
            try:
                service.persist(
                    candidates=result,
                    run_id=run_id,
                    selection_run_id=selection_run_id,
                    seen_at=started_at,
                )
            except Exception as exc:
                await bus.publish(
                    DomainEvent.create(
                        event_type=POLYMARKET_WHALE_MARKETS_PERSIST_FAILED,
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
                    event_type=POLYMARKET_WHALE_MARKETS_PERSIST_COMPLETED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "selection_run_id": selection_run_id,
                        "candidate_count": len(result.candidates),
                        "position_count": len(result.positions),
                        "error_count": len(result.errors),
                        "min_whale_count": self.min_whale_count,
                    },
                    metadata=metadata,
                )
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_COMPLETED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "selection_run_id": selection_run_id,
                        "candidate_count": len(result.candidates),
                        "position_count": len(result.positions),
                        "error_count": len(result.errors),
                        "min_whale_count": self.min_whale_count,
                        "partial": bool(result.errors),
                    },
                    metadata=metadata,
                )
            )
            return result
        except Exception as exc:
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_FAILED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
                        "selection_run_id": selection_run_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    metadata=metadata,
                )
            )
            raise


PolymarketWhaleMarketsBinding = PolymarketWhaleMarketCandidatesBinding


def _error_summary(errors) -> list[dict[str, int | str]]:
    messages = Counter(error.message for error in errors)
    return [
        {"message": message, "count": count}
        for message, count in messages.most_common()
    ]
