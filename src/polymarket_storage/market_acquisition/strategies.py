from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from polymarket_storage.market_acquisition.domain import CollectedMarkets
from polymarket_storage.market_acquisition.helpers import collect_wallet_markets
from polymarket_storage.polymarket.client import PolymarketDataClient
from polymarket_storage.polymarket.params.leaderboard.leaderboard import (
    LeaderboardParams,
)


LeaderboardOrder = Literal["PNL", "VOL"]


@dataclass(frozen=True)
class LeaderboardEntry:
    proxy_wallet: str
    row: dict[str, Any]


class LeaderboardCurrentPositionsStrategy(BaseModel):
    name: str = "leaderboard_current_positions"
    wallet_count: int = Field(default=25, ge=1, le=1000)
    leaderboard_category: str = "OVERALL"
    leaderboard_time_period: str = "DAY"
    leaderboard_limit: int = Field(default=50, ge=1, le=50)

    def params(self) -> dict[str, Any]:
        return self.model_dump()

    async def run(
        self,
        *,
        client: PolymarketDataClient,
        generated_at: datetime,
    ) -> CollectedMarkets:
        pnl_entries, volume_entries = await fetch_leaderboards(
            client=client,
            strategy=self,
        )
        wallets = select_intersection_wallets(
            pnl_entries=pnl_entries,
            volume_entries=volume_entries,
            wallet_count=self.wallet_count,
        )
        markets, errors = await collect_wallet_markets(client=client, wallets=wallets)
        return CollectedMarkets(
            markets=markets,
            errors=errors,
            checked_market_count=len(markets),
            generated_at=generated_at,
        )


async def fetch_leaderboards(
    *,
    client: PolymarketDataClient,
    strategy: LeaderboardCurrentPositionsStrategy,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    return await asyncio.gather(
        fetch_leaderboard(client=client, strategy=strategy, order_by="PNL"),
        fetch_leaderboard(client=client, strategy=strategy, order_by="VOL"),
    )


async def fetch_leaderboard(
    *,
    client: PolymarketDataClient,
    strategy: LeaderboardCurrentPositionsStrategy,
    order_by: LeaderboardOrder,
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    offset = 0
    max_offset = 1000

    while len(entries) < strategy.wallet_count and offset <= max_offset:
        params = LeaderboardParams(
            category=strategy.leaderboard_category,
            timePeriod=strategy.leaderboard_time_period,
            orderBy=order_by,
            limit=strategy.leaderboard_limit,
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
            if len(entries) >= strategy.wallet_count:
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


def build_strategy(name: str) -> LeaderboardCurrentPositionsStrategy:
    if name == "leaderboard_current_positions":
        return LeaderboardCurrentPositionsStrategy()

    raise ValueError(f"Unknown market collector strategy: {name}")
