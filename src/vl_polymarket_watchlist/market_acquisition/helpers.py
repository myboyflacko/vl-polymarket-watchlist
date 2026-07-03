from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

from vl_polymarket_watchlist.market_acquisition.domain import Market, MarketCollectionError
from vl_polymarket_watchlist.polymarket.client import PolymarketDataClient
from vl_polymarket_watchlist.polymarket.params.profile.current_positions import (
    CurrentPositionsParams,
)


MAX_POSITION_OFFSET = 10_000
POSITION_PAGE_LIMIT = 500


@dataclass(frozen=True)
class WalletMarketResult:
    markets: list[Market]
    errors: list[MarketCollectionError]


async def collect_wallet_markets(
    *,
    client: PolymarketDataClient,
    wallets: list[str],
) -> tuple[list[Market], list[MarketCollectionError]]:
    results = await asyncio.gather(
        *[_collect_wallet_markets(client=client, wallet=wallet) for wallet in wallets]
    )
    markets = [market for result in results for market in result.markets]
    errors = [error for result in results for error in result.errors]
    return deduplicate_markets(markets), errors


def deduplicate_markets(markets: list[Market]) -> list[Market]:
    return list({market.token_id: market for market in markets}.values())


async def _collect_wallet_markets(
    *,
    client: PolymarketDataClient,
    wallet: str,
) -> WalletMarketResult:
    rows: list[dict[str, Any]] = []
    offset = 0

    try:
        while offset <= MAX_POSITION_OFFSET:
            params = CurrentPositionsParams(
                user=wallet,
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
        return WalletMarketResult(
            markets=[],
            errors=[MarketCollectionError(source=wallet, message=str(exc))],
        )

    markets: list[Market] = []
    errors: list[MarketCollectionError] = []
    for row in rows:
        try:
            markets.append(normalize_position_market(row))
        except ValueError as exc:
            errors.append(MarketCollectionError(source=wallet, message=str(exc)))

    return WalletMarketResult(markets=deduplicate_markets(markets), errors=errors)


def normalize_position_market(row: dict[str, Any]) -> Market:
    return Market(
        token_id=required_string(row, "asset"),
        condition_id=required_string(row, "conditionId"),
        title=str(row.get("title") or ""),
        slug=str(row.get("slug") or ""),
        outcome=str(row.get("outcome") or ""),
        opposite_token_id=optional_string(row.get("oppositeAsset")),
        opposite_outcome=optional_string(row.get("oppositeOutcome")),
        end_date=optional_date(row.get("endDate")),
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


def optional_date(value: Any) -> date | None:
    if value is None:
        return None

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
