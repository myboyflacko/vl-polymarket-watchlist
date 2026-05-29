from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from void_liquidity.adapters.polymarket.api import (
    PolymarketDataClient,
    get_polymarket_data_client,
)
from void_liquidity.adapters.polymarket.api.params import CurrentPositionsParams
from void_liquidity.adapters.polymarket.discovery.whales_v2.repository import (
    list_tracked_whale_wallets,
)
from void_liquidity.adapters.polymarket.markets.whales.domain import (
    MarketCandidate,
    WhaleMarketCandidates,
    WhalePosition,
    WhalePositionCollectionError,
)


MAX_POSITION_OFFSET = 10_000
POSITION_PAGE_LIMIT = 500
DEFAULT_MIN_WHALE_COUNT = 3


@dataclass(frozen=True)
class _WalletPositionResult:
    positions: list[WhalePosition]
    errors: list[WhalePositionCollectionError]


async def collect_whale_market_candidates(
    *,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
) -> WhaleMarketCandidates:
    wallets = list_tracked_whale_wallets()
    if not wallets:
        return WhaleMarketCandidates()

    client = get_polymarket_data_client()
    results = await asyncio.gather(
        *(_collect_wallet_positions(client=client, proxy_wallet=wallet) for wallet in wallets)
    )

    positions = [
        position
        for result in results
        for position in result.positions
    ]
    errors = [
        error
        for result in results
        for error in result.errors
    ]

    return WhaleMarketCandidates(
        candidates=build_market_candidates(
            positions,
            min_whale_count=min_whale_count,
        ),
        positions=positions,
        errors=errors,
    )


def build_market_candidates(
    positions: Iterable[WhalePosition],
    *,
    min_whale_count: int = DEFAULT_MIN_WHALE_COUNT,
) -> list[MarketCandidate]:
    grouped: dict[str, list[WhalePosition]] = defaultdict(list)
    for position in positions:
        grouped[position.token_id].append(position)

    candidates = [
        candidate
        for token_id, group_positions in grouped.items()
        if (
            candidate := _build_market_candidate(
                token_id=token_id,
                positions=group_positions,
            )
        ).whale_count
        >= min_whale_count
    ]
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.whale_count,
            candidate.total_current_value,
        ),
        reverse=True,
    )


async def _collect_wallet_positions(
    *,
    client: PolymarketDataClient,
    proxy_wallet: str,
) -> _WalletPositionResult:
    rows: list[dict[str, Any]] = []
    errors: list[WhalePositionCollectionError] = []
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
        return _WalletPositionResult(
            positions=[],
            errors=[
                WhalePositionCollectionError(
                    proxy_wallet=proxy_wallet,
                    message=str(exc),
                )
            ],
        )

    positions: list[WhalePosition] = []
    for row in rows:
        try:
            positions.append(_normalize_position(proxy_wallet=proxy_wallet, row=row))
        except ValueError as exc:
            errors.append(
                WhalePositionCollectionError(
                    proxy_wallet=proxy_wallet,
                    message=str(exc),
                )
            )

    return _WalletPositionResult(positions=positions, errors=errors)


def _build_market_candidate(
    *,
    token_id: str,
    positions: list[WhalePosition],
) -> MarketCandidate:
    first_position = positions[0]
    total_size = sum(position.size for position in positions)
    total_current_value = sum(position.current_value for position in positions)
    wallets = list(dict.fromkeys(position.proxy_wallet for position in positions))
    weighted_avg_price = (
        sum(position.avg_price * position.size for position in positions) / total_size
        if total_size
        else 0.0
    )

    return MarketCandidate(
        token_id=token_id,
        condition_id=first_position.condition_id,
        title=first_position.title,
        slug=first_position.slug,
        outcome=first_position.outcome,
        whale_count=len(wallets),
        wallets=wallets,
        total_size=total_size,
        total_current_value=total_current_value,
        weighted_avg_price=weighted_avg_price,
        cur_price=first_position.cur_price,
        opposite_token_id=first_position.opposite_token_id,
        opposite_outcome=first_position.opposite_outcome,
        end_date=first_position.end_date,
        negative_risk=first_position.negative_risk,
    )


def _normalize_position(*, proxy_wallet: str, row: dict[str, Any]) -> WhalePosition:
    token_id = _required_string(row, "asset")
    condition_id = _required_string(row, "conditionId")

    return WhalePosition(
        proxy_wallet=proxy_wallet,
        token_id=token_id,
        condition_id=condition_id,
        outcome=str(row.get("outcome") or ""),
        outcome_index=_optional_int(row.get("outcomeIndex")),
        title=str(row.get("title") or ""),
        slug=str(row.get("slug") or ""),
        size=_float(row.get("size")),
        current_value=_float(row.get("currentValue")),
        avg_price=_float(row.get("avgPrice")),
        cur_price=_float(row.get("curPrice")),
        opposite_token_id=_optional_string(row.get("oppositeAsset")),
        opposite_outcome=_optional_string(row.get("oppositeOutcome")),
        end_date=_optional_date(row.get("endDate")),
        negative_risk=bool(row.get("negativeRisk", False)),
    )


def _required_string(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or str(value) == "":
        raise ValueError(f"position missing required field {key}")

    return str(value)


def _optional_string(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None

    return str(value)


def _float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
