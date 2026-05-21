import httpx
from typing import Any
from void_liquidity.adapters.polymarket.params.leaderboard import LeaderboardParams
from void_liquidity.settings import Settings
from void_liquidity.adapters.polymarket.client import HTTPClient
from void_liquidity.util.log import VoidLogger

settings = Settings()
logger = VoidLogger(__name__)

async def get_leaderboard(
    client: HTTPClient,
    params: LeaderboardParams = LeaderboardParams(),
) -> dict[str, Any] | list[Any] | None:

    base_url = settings.polymarket.data_api
    endpoint = "/v1/leaderboard"

    try:
        query_params = params.output_params()

        return await client.get(
            base_url=base_url,
            endpoint=endpoint,
            params=query_params,
        )

    except Exception as exc:
        logger.log_error(
            event="polymarket.get_leaderboard_failed",
            exc=exc,
            endpoint=endpoint,
            params=params.model_dump(exclude_none=True),
        )

        return None
