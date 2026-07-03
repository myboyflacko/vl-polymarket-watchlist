from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from vl_polymarket_watchlist.data.markets.market import (
    CollectedMarkets,
    ConditionPayload,
    MarketCollectionError,
    MarketObservation,
    TokenPayload,
)
from vl_polymarket_watchlist.source.client import PolymarketDataClient
from vl_polymarket_watchlist.source.params.leaderboard.leaderboard import (
    LeaderboardParams,
)
from vl_polymarket_watchlist.source.params.profile.current_positions import (
    CurrentPositionsParams,
)


LeaderboardOrder = Literal["PNL", "VOL"]
MAX_POSITION_OFFSET = 10_000
POSITION_PAGE_LIMIT = 500


@dataclass(frozen=True)
class LeaderboardEntry:
    proxy_wallet: str
    row: dict[str, Any]


@dataclass(frozen=True)
class WalletMarketResult:
    observations: list[MarketObservation]
    errors: list[MarketCollectionError]


class WhaleDiscoverySource(BaseModel):
    source: str = "whale_discovery"
    source_version: str = "leaderboard_current_positions_v1"
    wallet_count: int = Field(default=25, ge=1, le=1000)
    leaderboard_category: str = "OVERALL"
    leaderboard_time_period: str = "DAY"
    leaderboard_limit: int = Field(default=50, ge=1, le=50)

    def config(self) -> dict[str, Any]:
        return self.model_dump()

    async def run(
        self,
        *,
        client: PolymarketDataClient,
        generated_at: datetime,
    ) -> CollectedMarkets:
        pnl_entries, volume_entries = await fetch_leaderboards(
            client=client,
            source=self,
        )
        wallets = select_intersection_wallets(
            pnl_entries=pnl_entries,
            volume_entries=volume_entries,
            wallet_count=self.wallet_count,
        )
        observations, errors = await collect_wallet_market_observations(
            client=client,
            wallets=wallets,
            source=self.source,
            observed_at=generated_at,
        )
        return CollectedMarkets(
            observations=observations,
            errors=errors,
            checked_count=len(wallets),
            generated_at=generated_at,
        )


async def fetch_leaderboards(
    *,
    client: PolymarketDataClient,
    source: WhaleDiscoverySource,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    return await asyncio.gather(
        fetch_leaderboard(client=client, source=source, order_by="PNL"),
        fetch_leaderboard(client=client, source=source, order_by="VOL"),
    )


async def fetch_leaderboard(
    *,
    client: PolymarketDataClient,
    source: WhaleDiscoverySource,
    order_by: LeaderboardOrder,
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    offset = 0
    max_offset = 1000

    while len(entries) < source.wallet_count and offset <= max_offset:
        params = LeaderboardParams(
            category=source.leaderboard_category,
            timePeriod=source.leaderboard_time_period,
            orderBy=order_by,
            limit=source.leaderboard_limit,
            offset=offset,
        )
        page = await client.get_leaderboard(params)
        if not isinstance(page, list) or not page:
            break

        for row in page:
            entry = parse_leaderboard_entry(row)
            if entry is None:
                continue

            entries.setdefault(entry.proxy_wallet, entry.row)
            if len(entries) >= source.wallet_count:
                break

        if len(page) < params.limit:
            break

        offset += params.limit

    return entries


def select_intersection_wallets(
    *,
    pnl_entries: dict[str, dict[str, Any]],
    volume_entries: dict[str, dict[str, Any]],
    wallet_count: int,
) -> list[str]:
    volume_wallets = set(volume_entries)
    return [wallet for wallet in pnl_entries if wallet in volume_wallets][:wallet_count]


def parse_leaderboard_entry(row: Any) -> LeaderboardEntry | None:
    if not isinstance(row, dict):
        return None

    proxy_wallet = row.get("proxyWallet")
    if not isinstance(proxy_wallet, str):
        return None

    return LeaderboardEntry(proxy_wallet=proxy_wallet, row=row)


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
