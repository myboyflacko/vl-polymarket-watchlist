from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales import (
    collect_whale_market_candidates,
    persist_market_candidates,
)
from void_liquidity.adapters.polymarket.markets.whales.collector import (
    DEFAULT_MIN_WHALE_COUNT,
)
from void_liquidity.adapters.polymarket.markets.whales.domain import (
    WhaleMarketCandidates,
)
from void_liquidity.adapters.polymarket.markets.whales.events import (
    POLYMARKET_WHALE_MARKETS_COMPLETED,
    POLYMARKET_WHALE_MARKETS_DISCOVERED,
    POLYMARKET_WHALE_MARKETS_FAILED,
    POLYMARKET_WHALE_MARKETS_PERSIST_COMPLETED,
    POLYMARKET_WHALE_MARKETS_PERSIST_FAILED,
    POLYMARKET_WHALE_MARKETS_PERSIST_STARTED,
    POLYMARKET_WHALE_MARKETS_REQUESTED,
    POLYMARKET_WHALE_MARKETS_STARTED,
)
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.core.events import DomainEvent, EventBus


EVENT_SOURCE = "binding.polymarket.markets.whales"
ADAPTER_NAME = "polymarket.markets.whales"
PROVIDER_NAME = "polymarket"


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


class PolymarketWhaleMarketsBinding:
    spec = BindingSpec(
        name="polymarket.markets.whales",
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

    async def handle(self, event: DomainEvent, bus: EventBus) -> WhaleMarketCandidates:
        started_at = datetime.now(UTC)
        run_id = _build_run_id(started_at)
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
                    payload={"run_id": run_id},
                    metadata=metadata,
                )
            )

            result = await collect_whale_market_candidates(
                min_whale_count=self.min_whale_count,
            )
            await bus.publish(
                DomainEvent.create(
                    event_type=POLYMARKET_WHALE_MARKETS_DISCOVERED,
                    source=EVENT_SOURCE,
                    correlation_id=event.correlation_id,
                    payload={
                        "run_id": run_id,
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
                        "candidate_count": len(result.candidates),
                        "position_count": len(result.positions),
                        "error_count": len(result.errors),
                        "min_whale_count": self.min_whale_count,
                    },
                    metadata=metadata,
                )
            )
            try:
                persist_market_candidates(
                    result.candidates,
                    run_id=run_id,
                    min_whale_count=self.min_whale_count,
                    position_count=len(result.positions),
                    error_count=len(result.errors),
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
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    metadata=metadata,
                )
            )
            raise


def _error_summary(errors) -> list[dict[str, int | str]]:
    messages = Counter(error.message for error in errors)
    return [
        {"message": message, "count": count}
        for message, count in messages.most_common()
    ]
