import asyncio
from datetime import UTC, datetime
from typing import Any

from vl_polymarket_watchlist.markets.discovery.strategies.whale_leaderboard import (
    WhaleDiscoverySource,
    select_intersection_wallets,
)


NOW = datetime(2026, 6, 1, tzinfo=UTC)
WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
WALLET_THREE = "0xcccccccccccccccccccccccccccccccccccccccc"


class FakePolymarketClient:
    def __init__(self) -> None:
        self.position_wallets: list[str] = []

    async def get_leaderboard(self, params: Any) -> list[dict[str, Any]]:
        if params.orderBy == "PNL":
            return [
                {"proxyWallet": WALLET_ONE},
                {"proxyWallet": WALLET_TWO},
            ]

        return [
            {"proxyWallet": WALLET_TWO},
            {"proxyWallet": WALLET_THREE},
        ]

    async def get_current_positions(self, params: Any) -> list[dict[str, Any]]:
        self.position_wallets.append(params.user)
        return [
            {
                "asset": "token-yes",
                "conditionId": "condition-1",
                "title": "Market title",
                "slug": "market-title",
                "outcome": "Yes",
                "oppositeAsset": "token-no",
                "oppositeOutcome": "No",
                "endDate": "2026-12-31T00:00:00Z",
            }
        ]


def test_select_intersection_wallets_keeps_only_pnl_and_volume_wallets() -> None:
    wallets = select_intersection_wallets(
        pnl_entries={WALLET_ONE: {}, WALLET_TWO: {}},
        volume_entries={WALLET_TWO: {}, WALLET_THREE: {}},
        wallet_count=10,
    )

    assert wallets == [WALLET_TWO]


def test_whale_discovery_collects_only_intersection_wallet_observations() -> None:
    client = FakePolymarketClient()
    source = WhaleDiscoverySource(wallet_count=10)

    result = asyncio.run(source.run(client=client, generated_at=NOW))

    assert client.position_wallets == [WALLET_TWO]
    assert result.checked_count == 1
    assert result.observed_count == 1
    assert result.observations[0].condition.condition_id == "condition-1"
    assert result.observations[0].token.token_id == "token-yes"
