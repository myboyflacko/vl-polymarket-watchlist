from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from whale_tracker.core.time import ensure_utc
from whale_tracker.providers.polymarket.client import PolymarketDataClient
from whale_tracker.providers.polymarket.params.profile.trades import TradesParams
from whale_tracker.tracker.trades.domain import (
    Trade,
    TradeCollectionError,
    TradeSource,
)


MAX_TRADE_OFFSET = 10_000
TRADE_PAGE_LIMIT = 10_000


@dataclass(frozen=True)
class SourceTradeResult:
    trades: list[Trade]
    errors: list[TradeCollectionError]


async def collect_position_trades(
    *,
    client: PolymarketDataClient,
    sources: list[TradeSource],
    generated_at: datetime,
) -> tuple[list[Trade], list[TradeCollectionError]]:
    results = await asyncio.gather(
        *[
            _collect_source_trades(
                client=client,
                source=source,
                generated_at=generated_at,
            )
            for source in sources
        ]
    )
    return (
        [trade for result in results for trade in result.trades],
        [error for result in results for error in result.errors],
    )


async def _collect_source_trades(
    *,
    client: PolymarketDataClient,
    source: TradeSource,
    generated_at: datetime,
) -> SourceTradeResult:
    rows: list[dict[str, Any]] = []
    errors: list[TradeCollectionError] = []
    offset = 0

    try:
        while offset <= MAX_TRADE_OFFSET:
            params = TradesParams(
                user=source.proxy_wallet,
                market=[source.condition_id],
                limit=TRADE_PAGE_LIMIT,
                offset=offset,
            )
            page = await client.get_trades(params)
            if not isinstance(page, list) or not page:
                break

            rows.extend(row for row in page if isinstance(row, dict))
            if len(page) < params.limit:
                break

            offset += params.limit

    except Exception as exc:
        return SourceTradeResult(
            trades=[],
            errors=[
                TradeCollectionError(
                    proxy_wallet=source.proxy_wallet,
                    condition_id=source.condition_id,
                    message=str(exc),
                )
            ],
        )

    trades: list[Trade] = []
    for row in rows:
        try:
            trades.append(
                normalize_trade(
                    source=source,
                    row=row,
                    generated_at=generated_at,
                )
            )
        except ValueError as exc:
            errors.append(
                TradeCollectionError(
                    proxy_wallet=source.proxy_wallet,
                    condition_id=source.condition_id,
                    message=str(exc),
                )
            )

    return SourceTradeResult(trades=trades, errors=errors)


def normalize_trade(
    *,
    source: TradeSource,
    row: dict[str, Any],
    generated_at: datetime,
) -> Trade:
    token_id = optional_string(
        first_present(
            row,
            "asset",
            "asset_id",
            "token_id",
            "tokenId",
            "outcomeTokenId",
        )
    )
    price = optional_float(first_present(row, "price", "avgPrice"))
    size = optional_float(first_present(row, "size", "amount"))
    value = optional_float(first_present(row, "value", "currentValue", "usdcSize"))
    if value is None and price is not None and size is not None:
        value = price * size

    trade_timestamp = optional_datetime(
        first_present(row, "timestamp", "createdAt", "created_at", "time")
    )
    transaction_hash = optional_string(
        first_present(row, "transactionHash", "transaction_hash", "txHash", "hash")
    )

    return Trade(
        proxy_wallet=source.proxy_wallet,
        condition_id=source.condition_id,
        trade_key=build_trade_key(
            source=source,
            row=row,
            token_id=token_id,
            trade_timestamp=trade_timestamp,
            transaction_hash=transaction_hash,
        ),
        market_id=source.market_ids_by_token.get(token_id or ""),
        token_id=token_id,
        side=optional_upper(first_present(row, "side")),
        outcome=optional_string(first_present(row, "outcome")),
        price=price,
        size=size,
        value=value,
        trade_timestamp=trade_timestamp,
        transaction_hash=transaction_hash,
        raw_payload=row,
        generated_at=ensure_utc(generated_at),
    )


def build_trade_key(
    *,
    source: TradeSource,
    row: dict[str, Any],
    token_id: str | None,
    trade_timestamp: datetime | None,
    transaction_hash: str | None,
) -> str:
    api_id = optional_string(first_present(row, "id", "tradeId", "trade_id"))
    if api_id:
        return f"api:{api_id}"

    if transaction_hash:
        log_index = optional_string(first_present(row, "logIndex", "log_index"))
        if log_index:
            return f"tx:{transaction_hash}:{log_index}"

    payload = {
        "wallet": source.proxy_wallet,
        "condition_id": source.condition_id,
        "token_id": token_id,
        "timestamp": trade_timestamp.isoformat() if trade_timestamp else None,
        "side": optional_upper(first_present(row, "side")),
        "price": optional_string(first_present(row, "price", "avgPrice")),
        "size": optional_string(first_present(row, "size", "amount")),
        "payload": row,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "hash:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value) != "":
            return value

    return None


def optional_string(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None

    return str(value)


def optional_upper(value: Any) -> str | None:
    string_value = optional_string(value)
    return string_value.upper() if string_value is not None else None


def optional_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    raw = str(value)
    try:
        timestamp = int(raw)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

        return ensure_utc(parsed)

    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000

    return datetime.fromtimestamp(timestamp, tz=UTC)
