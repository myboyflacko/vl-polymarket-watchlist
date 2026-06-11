from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from whale_tracker.providers.polymarket.client import PolymarketDataClient
from whale_tracker.tracker.markets.domain import Markets
from whale_tracker.tracker.markets.helpers import collect_wallet_positions
from whale_tracker.tracker.whales.repository import list_tracked_whale_wallets


class DefaultMarketDiscoveryProfile(BaseModel):
    name: str = "default_market_discovery"

    async def run(
        self,
        *,
        client: PolymarketDataClient,
        whales_run_id: str | None,
        generated_at: datetime,
    ) -> Markets:
        wallets = list_tracked_whale_wallets()
        if not wallets:
            return Markets(generated_at=generated_at)

        positions, errors = await collect_wallet_positions(
            client=client,
            wallets=wallets,
        )
        return Markets(
            positions=positions,
            errors=errors,
            checked_market_count=len(positions),
            generated_at=generated_at,
        )
