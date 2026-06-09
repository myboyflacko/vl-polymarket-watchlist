from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from whale_tracker.core.time import ensure_utc
from whale_tracker.providers.polymarket.params.orderbook import (
    OrderBookRequest,
    OrderBooksParams,
)
from whale_tracker.tracker.orderbooks.domain import (
    OrderBookCollectionError,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderBooks,
    TrackedMarketOrderBookSource,
)


class OrderBookDiscoveryProfile(BaseModel):
    depth: int = Field(default=5, ge=1)
    batch_size: int = Field(default=100, ge=1)

    async def run(
        self,
        *,
        client: Any,
        sources: list[TrackedMarketOrderBookSource],
        generated_at: datetime,
    ) -> OrderBooks:
        generated_at = ensure_utc(generated_at)
        if not sources:
            return OrderBooks(
                generated_at=generated_at,
                depth=self.depth,
                checked_market_count=0,
            )

        snapshots: list[OrderBookSnapshot] = []
        errors: list[OrderBookCollectionError] = []

        for batch in _batches(sources, self.batch_size):
            try:
                response = await client.get_order_books(
                    OrderBooksParams(
                        root=[
                            OrderBookRequest(token_id=source.token_id)
                            for source in batch
                        ]
                    )
                )
            except Exception as exc:
                errors.extend(
                    OrderBookCollectionError(
                        token_id=source.token_id,
                        message=str(exc),
                    )
                    for source in batch
                )
                continue

            if not isinstance(response, list):
                errors.extend(
                    OrderBookCollectionError(
                        token_id=source.token_id,
                        message="Orderbook response was not a list.",
                    )
                    for source in batch
                )
                continue

            snapshots_by_token = {
                str(item.get("asset_id", "")): item
                for item in response
                if isinstance(item, dict)
            }
            for source in batch:
                item = snapshots_by_token.get(source.token_id)
                if item is None:
                    errors.append(
                        OrderBookCollectionError(
                            token_id=source.token_id,
                            message="Orderbook response missing token.",
                        )
                    )
                    continue

                snapshots.append(
                    _snapshot_from_response(
                        source=source,
                        item=item,
                        generated_at=generated_at,
                        depth=self.depth,
                    )
                )

        return OrderBooks(
            snapshots=snapshots,
            errors=errors,
            checked_market_count=len(sources),
            generated_at=generated_at,
            depth=self.depth,
        )


def _batches(
    sources: list[TrackedMarketOrderBookSource],
    batch_size: int,
) -> list[list[TrackedMarketOrderBookSource]]:
    return [
        sources[index : index + batch_size]
        for index in range(0, len(sources), batch_size)
    ]


def _snapshot_from_response(
    *,
    source: TrackedMarketOrderBookSource,
    item: dict[str, Any],
    generated_at: datetime,
    depth: int,
) -> OrderBookSnapshot:
    bids = _levels(item.get("bids"), depth)
    asks = _levels(item.get("asks"), depth)
    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    spread = (
        best_ask - best_bid
        if best_bid is not None and best_ask is not None
        else None
    )
    midpoint = (
        (best_bid + best_ask) / 2
        if best_bid is not None and best_ask is not None
        else None
    )
    timestamp_raw = _string_or_none(item.get("timestamp"))

    return OrderBookSnapshot(
        tracked_market_id=source.tracked_market_id,
        token_id=source.token_id,
        condition_id=source.condition_id,
        market=str(item.get("market") or source.condition_id),
        exchange_timestamp=_parse_exchange_timestamp(timestamp_raw),
        exchange_timestamp_raw=timestamp_raw,
        book_hash=str(item.get("hash") or ""),
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        midpoint=midpoint,
        min_order_size=_float_or_none(item.get("min_order_size")),
        tick_size=_float_or_none(item.get("tick_size")),
        negative_risk=bool(item.get("neg_risk", False)),
        last_trade_price=_float_or_none(item.get("last_trade_price")),
        generated_at=generated_at,
    )


def _levels(raw_levels: object, depth: int) -> list[OrderBookLevel]:
    if not isinstance(raw_levels, list):
        return []

    levels: list[OrderBookLevel] = []
    for raw_level in raw_levels[:depth]:
        if not isinstance(raw_level, dict):
            continue

        price = _float_or_none(raw_level.get("price"))
        size = _float_or_none(raw_level.get("size"))
        if price is None or size is None:
            continue

        levels.append(OrderBookLevel(price=price, size=size))

    return levels


def _parse_exchange_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None

    try:
        timestamp = int(value)
    except ValueError:
        return None

    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000

    return datetime.fromtimestamp(timestamp, tz=UTC)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None

    return str(value)
