from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from vl_polymarket_watchlist.data.orderbooks.market import (
    PARSER_VERSION,
    ParsedOrderBook,
)


def parse_orderbook_payload(
    *,
    condition_id: str,
    token_id: str,
    payload: dict[str, Any],
    generated_at: datetime,
) -> ParsedOrderBook:
    bids = _levels(payload.get("bids"))
    asks = _levels(payload.get("asks"))
    best_bid = max((level["price"] for level in bids), default=None)
    best_ask = min((level["price"] for level in asks), default=None)
    spread = (
        best_ask - best_bid
        if best_bid is not None and best_ask is not None
        else None
    )
    midpoint = (
        (best_bid + best_ask) / Decimal("2")
        if best_bid is not None and best_ask is not None
        else None
    )
    invalid_reason = _invalid_reason(
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
    )
    return ParsedOrderBook(
        condition_id=condition_id,
        token_id=token_id,
        generated_at=generated_at,
        exchange_timestamp=_exchange_timestamp(payload.get("timestamp")),
        exchange_timestamp_raw=_optional_string(payload.get("timestamp")),
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=midpoint,
        spread=spread,
        last_trade_price=_decimal(payload.get("last_trade_price")),
        bid_depth_top_1=_depth(bids, 1),
        ask_depth_top_1=_depth(asks, 1),
        bid_depth_top_3=_depth(bids, 3),
        ask_depth_top_3=_depth(asks, 3),
        bid_depth_top_5=_depth(bids, 5),
        ask_depth_top_5=_depth(asks, 5),
        bid_levels_count=len(bids),
        ask_levels_count=len(asks),
        min_order_size=_decimal(payload.get("min_order_size")),
        tick_size=_decimal(payload.get("tick_size")),
        negative_risk=_optional_bool(payload.get("neg_risk")),
        bids=[_dump_level(level) for level in bids],
        asks=[_dump_level(level) for level in asks],
        book_hash=_optional_string(payload.get("hash")),
        valid_orderbook=invalid_reason is None,
        invalid_reason=invalid_reason,
        parser_version=PARSER_VERSION,
        raw_payload=payload,
    )


def _levels(value: Any) -> list[dict[str, Decimal]]:
    if not isinstance(value, list):
        return []

    levels = []
    for row in value:
        if not isinstance(row, dict):
            continue

        price = _decimal(row.get("price"))
        size = _decimal(row.get("size"))
        if price is None or size is None:
            continue

        levels.append({"price": price, "size": size})
    return levels


def _invalid_reason(
    *,
    bids: list[dict[str, Decimal]],
    asks: list[dict[str, Decimal]],
    best_bid: Decimal | None,
    best_ask: Decimal | None,
    spread: Decimal | None,
) -> str | None:
    if not bids:
        return "missing_bids"

    if not asks:
        return "missing_asks"

    if best_bid is None or best_ask is None or spread is None:
        return "missing_best_prices"

    if best_bid > best_ask:
        return "crossed_orderbook"

    if spread < 0:
        return "negative_spread"

    if best_bid <= 0:
        return "best_bid_not_positive"

    if best_ask >= 1:
        return "best_ask_not_below_one"

    return None


def _depth(levels: list[dict[str, Decimal]], count: int) -> Decimal:
    return sum((level["size"] for level in levels[:count]), Decimal("0"))


def _decimal(value: Any) -> Decimal | None:
    if value is None or str(value) == "":
        return None

    try:
        return Decimal(str(value))
    except Exception:
        return None


def _exchange_timestamp(value: Any) -> datetime | None:
    if value is None or str(value) == "":
        return None

    try:
        timestamp = int(str(value))
    except ValueError:
        return None

    if timestamp > 10_000_000_000:
        timestamp = timestamp // 1000

    return datetime.fromtimestamp(timestamp, tz=UTC)


def _optional_string(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None

    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}

    return bool(value)


def _dump_level(level: dict[str, Decimal]) -> dict[str, str]:
    return {
        "price": str(level["price"]),
        "size": str(level["size"]),
    }
