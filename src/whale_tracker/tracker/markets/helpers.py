from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

from whale_tracker.providers.polymarket.client import PolymarketDataClient
from whale_tracker.providers.polymarket.params.profile.current_positions import (
    CurrentPositionsParams,
)
from whale_tracker.tracker.markets.domain import (
    MarketPositionCollectionError,
    WhalePosition,
)


MAX_POSITION_OFFSET = 10_000
POSITION_PAGE_LIMIT = 500


@dataclass(frozen=True)
class WalletPositionResult:
    positions: list[WhalePosition]
    errors: list[MarketPositionCollectionError]


async def collect_wallet_positions(
    *,
    client: PolymarketDataClient,
    wallets: list[str],
) -> tuple[list[WhalePosition], list[MarketPositionCollectionError]]:
    results = await asyncio.gather(
        *[
            _collect_wallet_positions(client=client, proxy_wallet=wallet)
            for wallet in wallets
        ]
    )
    return (
        [
            position
            for result in results
            for position in result.positions
        ],
        [
            error
            for result in results
            for error in result.errors
        ],
    )


async def _collect_wallet_positions(
    *,
    client: PolymarketDataClient,
    proxy_wallet: str,
) -> WalletPositionResult:
    rows: list[dict[str, Any]] = []
    errors: list[MarketPositionCollectionError] = []
    offset = 0

    try:
        while offset <= MAX_POSITION_OFFSET:
            params = CurrentPositionsParams(
                user=proxy_wallet,
                limit=POSITION_PAGE_LIMIT,
                offset=offset,
                sortBy="CURRENT",
                sortDirection="DESC",
            )
            page = await client.get_current_positions(params)
            if not isinstance(page, list) or not page:
                break

            rows.extend(row for row in page if isinstance(row, dict))
            if len(page) < params.limit:
                break

            offset += params.limit

    except Exception as exc:
        return WalletPositionResult(
            positions=[],
            errors=[
                MarketPositionCollectionError(
                    proxy_wallet=proxy_wallet,
                    message=str(exc),
                )
            ],
        )

    positions: list[WhalePosition] = []
    for row in rows:
        try:
            positions.append(normalize_position(proxy_wallet=proxy_wallet, row=row))
        except ValueError as exc:
            errors.append(
                MarketPositionCollectionError(
                    proxy_wallet=proxy_wallet,
                    message=str(exc),
                )
            )

    return WalletPositionResult(positions=positions, errors=errors)


def normalize_position(*, proxy_wallet: str, row: dict[str, Any]) -> WhalePosition:
    token_id = required_string(row, "asset")
    condition_id = required_string(row, "conditionId")

    return WhalePosition(
        proxy_wallet=proxy_wallet,
        token_id=token_id,
        condition_id=condition_id,
        outcome=str(row.get("outcome") or ""),
        outcome_index=optional_int(row.get("outcomeIndex")),
        title=str(row.get("title") or ""),
        slug=str(row.get("slug") or ""),
        size=to_float(row.get("size")),
        current_value=to_float(row.get("currentValue")),
        avg_price=to_float(row.get("avgPrice")),
        cur_price=to_float(row.get("curPrice")),
        opposite_token_id=optional_string(row.get("oppositeAsset")),
        opposite_outcome=optional_string(row.get("oppositeOutcome")),
        end_date=optional_date(row.get("endDate")),
        negative_risk=bool(row.get("negativeRisk", False)),
    )


def required_string(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or str(value) == "":
        raise ValueError(f"position missing required field {key}")

    return str(value)


def optional_string(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None

    return str(value)


def to_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def optional_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_date(value: Any) -> date | None:
    if value is None:
        return None

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
