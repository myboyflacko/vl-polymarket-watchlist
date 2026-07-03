from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from vl_polymarket_watchlist.market_acquisition.domain import (
    ConditionPayload,
    MarketCollectionError,
    MarketObservation,
    TokenPayload,
)
from vl_polymarket_watchlist.polymarket.client import PolymarketDataClient
from vl_polymarket_watchlist.polymarket.params.profile.current_positions import (
    CurrentPositionsParams,
)


MAX_POSITION_OFFSET = 10_000
POSITION_PAGE_LIMIT = 500


@dataclass(frozen=True)
class WalletMarketResult:
    observations: list[MarketObservation]
    errors: list[MarketCollectionError]


async def collect_wallet_market_observations(
    *,
    client: PolymarketDataClient,
    wallets: list[str],
    source: str,
    observed_at: datetime,
) -> tuple[list[MarketObservation], list[MarketCollectionError]]:
    results = await asyncio.gather(
        *[
            _collect_wallet_market_observations(
                client=client,
                wallet=wallet,
                source=source,
                observed_at=observed_at,
            )
            for wallet in wallets
        ]
    )
    observations = [
        observation
        for result in results
        for observation in result.observations
    ]
    errors = [error for result in results for error in result.errors]
    return deduplicate_observations(observations), errors


def deduplicate_observations(
    observations: list[MarketObservation],
) -> list[MarketObservation]:
    return list({observation.token.token_id: observation for observation in observations}.values())


async def _collect_wallet_market_observations(
    *,
    client: PolymarketDataClient,
    wallet: str,
    source: str,
    observed_at: datetime,
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
            observations=[],
            errors=[MarketCollectionError(source=wallet, message=str(exc))],
        )

    observations: list[MarketObservation] = []
    errors: list[MarketCollectionError] = []
    for row in rows:
        try:
            observations.append(
                normalize_position_observation(
                    row=row,
                    source=source,
                    observed_at=observed_at,
                )
            )
        except ValueError as exc:
            errors.append(MarketCollectionError(source=wallet, message=str(exc)))

    return WalletMarketResult(
        observations=deduplicate_observations(observations),
        errors=errors,
    )


def normalize_position_observation(
    *,
    row: dict[str, Any],
    source: str,
    observed_at: datetime,
) -> MarketObservation:
    condition_id = required_string(row, "conditionId")
    token_id = required_string(row, "asset")
    active = optional_bool(row.get("active"), default=True)
    closed = optional_bool(row.get("closed"), default=False)
    archived = optional_bool(row.get("archived"), default=False)
    enable_order_book = optional_bool(
        first_present(row, "enableOrderBook", "enable_order_book"),
        default=True,
    )

    condition = ConditionPayload(
        condition_id=condition_id,
        event_id=optional_string(first_present(row, "eventId", "event_id")),
        slug=optional_string(row.get("slug")),
        title=optional_string(row.get("title")),
        question=optional_string(first_present(row, "question", "title")),
        end_date=optional_datetime(first_present(row, "endDate", "end_date")),
        active=active,
        closed=closed,
        archived=archived,
        enable_order_book=enable_order_book,
        category=optional_string(row.get("category")),
        tags=optional_tags(row.get("tags")),
        raw_latest_payload=row,
    )
    token = TokenPayload(
        token_id=token_id,
        condition_id=condition_id,
        outcome=optional_string(row.get("outcome")),
        outcome_index=optional_int(first_present(row, "outcomeIndex", "outcome_index")),
        opposite_token_id=optional_string(
            first_present(row, "oppositeAsset", "opposite_token_id")
        ),
        opposite_outcome=optional_string(
            first_present(row, "oppositeOutcome", "opposite_outcome")
        ),
        active=active,
        closed=closed,
        enable_order_book=enable_order_book,
    )
    return MarketObservation(
        source=source,
        observed_at=observed_at,
        condition=condition,
        token=token,
        event_slug=optional_string(first_present(row, "eventSlug", "event_slug")),
        event_title=optional_string(first_present(row, "eventTitle", "event_title")),
        volume=optional_decimal(row.get("volume")),
        liquidity=optional_decimal(row.get("liquidity")),
        open_interest=optional_decimal(first_present(row, "openInterest", "open_interest")),
        last_trade_price=optional_decimal(
            first_present(row, "lastTradePrice", "last_trade_price")
        ),
        outcome_price=optional_decimal(first_present(row, "curPrice", "outcome_price")),
        source_reason=source,
        metadata_json={},
        raw_payload=row,
    )


def first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value

    return None


def required_string(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or str(value) == "":
        raise ValueError(f"position missing required field {key}")

    return str(value)


def optional_string(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None

    return str(value)


def optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value) == "":
        return None

    try:
        return Decimal(str(value))
    except Exception:
        return None


def optional_int(value: Any) -> int | None:
    if value is None or str(value) == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_bool(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}

    return bool(value)


def optional_datetime(value: Any) -> datetime | None:
    if value is None or str(value) == "":
        return None

    text = str(value)
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1]).replace(tzinfo=UTC)

        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def optional_tags(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]
