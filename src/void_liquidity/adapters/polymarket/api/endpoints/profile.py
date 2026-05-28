from typing import Any

from pydantic import Field

from void_liquidity.adapters.polymarket.api.client import HTTPClient
from void_liquidity.adapters.polymarket.api.data_client import get_polymarket_data_client
from void_liquidity.adapters.polymarket.api.errors import (
    PolymarketRateLimitError as PolymarketRateLimitError,
)
from void_liquidity.adapters.polymarket.api.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    TradesParams,
)
from void_liquidity.adapters.polymarket.api.params.base import BaseParams


class ProfileParams(BaseParams):
    address: str = Field(
        min_length=42,
        max_length=42,
        pattern=r"^0x[a-fA-F0-9]{40}$",
    )


async def get_closed_positions(
    client: HTTPClient,
    params: ClosedPositionsParams,
) -> dict[str, Any] | list[Any]:
    return await get_polymarket_data_client().get_closed_positions(params)


async def get_current_positions(
    client: HTTPClient,
    params: CurrentPositionsParams,
) -> dict[str, Any] | list[Any]:
    """Fetch current positions for a Polymarket user.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user
    """

    return await get_polymarket_data_client().get_current_positions(params)


async def get_activity(
    client: HTTPClient,
    params: ActivityParams,
) -> dict[str, Any] | list[Any]:
    """Fetch activity rows for a Polymarket user.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-user-activity
    """

    return await get_polymarket_data_client().get_activity(params)


async def get_trades(
    client: HTTPClient,
    params: TradesParams,
) -> dict[str, Any] | list[Any]:
    """Fetch trades for a Polymarket user or markets.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets
    """

    return await get_polymarket_data_client().get_trades(params)


get_profile = get_closed_positions
