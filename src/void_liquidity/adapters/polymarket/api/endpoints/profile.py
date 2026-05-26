import asyncio
from typing import Any

from pydantic import Field

from void_liquidity.adapters.polymarket.api.client import (
    HTTPClient,
    HTTPStatusCodeError,
)
from void_liquidity.adapters.polymarket.api.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    TradesParams,
)
from void_liquidity.adapters.polymarket.api.params.base import BaseParams
from void_liquidity.settings import Settings

settings = Settings()
profile_request_semaphore = asyncio.Semaphore(
    settings.polymarket.max_concurrent_profile_requests,
)


class PolymarketRateLimitError(RuntimeError):
    pass


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, HTTPStatusCodeError) and exc.status_code == 429


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
    return await _get_profile_endpoint(
        client=client,
        endpoint="/v1/closed-positions",
        params=params,
    )


async def get_current_positions(
    client: HTTPClient,
    params: CurrentPositionsParams,
) -> dict[str, Any] | list[Any]:
    """Fetch current positions for a Polymarket user.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user
    """

    return await _get_profile_endpoint(
        client=client,
        endpoint="/v1/positions",
        params=params,
    )


async def get_activity(
    client: HTTPClient,
    params: ActivityParams,
) -> dict[str, Any] | list[Any]:
    """Fetch activity rows for a Polymarket user.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-user-activity
    """

    return await _get_profile_endpoint(
        client=client,
        endpoint="/activity",
        params=params,
    )


async def get_trades(
    client: HTTPClient,
    params: TradesParams,
) -> dict[str, Any] | list[Any]:
    """Fetch trades for a Polymarket user or markets.

    Reference:
        https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets
    """

    return await _get_profile_endpoint(
        client=client,
        endpoint="/trades",
        params=params,
    )


async def _get_profile_endpoint(
    client: HTTPClient,
    endpoint: str,
    params: BaseParams,
) -> dict[str, Any] | list[Any]:
    base_url = settings.polymarket.data_api
    query_params = params.output_params()
    max_attempts = settings.polymarket.rate_limit_retry_attempts + 1

    for attempt in range(1, max_attempts + 1):
        try:
            async with profile_request_semaphore:
                if settings.polymarket.request_delay_seconds:
                    await asyncio.sleep(settings.polymarket.request_delay_seconds)

                return await client.get(
                    base_url=base_url,
                    endpoint=endpoint,
                    params=query_params,
                )

        except Exception as exc:
            is_rate_limited = _is_rate_limited(exc)

            if is_rate_limited and attempt < max_attempts:
                wait_seconds = settings.polymarket.rate_limit_backoff_seconds * attempt
                await asyncio.sleep(wait_seconds)
                continue

            if is_rate_limited:
                raise PolymarketRateLimitError(
                    f"Rate limited for {endpoint} after {attempt} attempts"
                ) from exc

            raise

    raise RuntimeError(f"Request attempts exhausted for {endpoint}")


get_profile = get_closed_positions
