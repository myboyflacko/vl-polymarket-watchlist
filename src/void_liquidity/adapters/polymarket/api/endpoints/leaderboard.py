from typing import Any

from void_liquidity.adapters.polymarket.api.client import HTTPClient
from void_liquidity.adapters.polymarket.api.data_client import get_polymarket_data_client
from void_liquidity.adapters.polymarket.api.params.leaderboard import LeaderboardParams


async def get_leaderboard(
    client: HTTPClient,
    params: LeaderboardParams = LeaderboardParams(),
) -> dict[str, Any] | list[Any]:

    return await get_polymarket_data_client().get_leaderboard(params)
