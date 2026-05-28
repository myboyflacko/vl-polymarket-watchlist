from typing import Any

from void_liquidity.adapters.polymarket.api.client import HTTPClient
from void_liquidity.adapters.polymarket.api.params.leaderboard import LeaderboardParams
from void_liquidity.adapters.polymarket.api.rate_limit import (
    PolymarketDataEndpoint,
    wait_for_data_api,
)
from void_liquidity.settings import Settings

settings = Settings()


async def get_leaderboard(
    client: HTTPClient,
    params: LeaderboardParams = LeaderboardParams(),
) -> dict[str, Any] | list[Any]:

    base_url = settings.polymarket.data_api
    endpoint = "/v1/leaderboard"
    query_params = params.output_params()

    await wait_for_data_api(PolymarketDataEndpoint.LEADERBOARD)
    return await client.get(
        base_url=base_url,
        endpoint=endpoint,
        params=query_params,
    )
