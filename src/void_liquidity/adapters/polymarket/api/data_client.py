from __future__ import annotations

import asyncio
from typing import Any

from void_liquidity.adapters.polymarket.api.client import (
    HTTPClient,
    HTTPStatusCodeError,
)
from void_liquidity.adapters.polymarket.api.errors import PolymarketRateLimitError
from void_liquidity.adapters.polymarket.api.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    LeaderboardParams,
    TradesParams,
)
from void_liquidity.adapters.polymarket.api.params.base import BaseParams
from void_liquidity.adapters.polymarket.api.rate_limit import (
    PolymarketDataEndpoint,
    wait_for_data_api,
)
from void_liquidity.settings import Settings


settings = Settings()

data_api_request_semaphore = asyncio.Semaphore(
    settings.polymarket.max_concurrent_profile_requests,
)


class PolymarketDataClient:
    def __init__(self, http_client: HTTPClient | None = None) -> None:
        self._client = http_client or HTTPClient()
        self._owns_client = http_client is None

    async def __aenter__(self) -> PolymarketDataClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def get_closed_positions(
        self,
        params: ClosedPositionsParams,
    ) -> dict[str, Any] | list[Any]:
        return await self._get_data_api_endpoint(
            endpoint="/v1/closed-positions",
            params=params,
            rate_limit_endpoint=PolymarketDataEndpoint.POSITIONS,
        )

    async def get_current_positions(
        self,
        params: CurrentPositionsParams,
    ) -> dict[str, Any] | list[Any]:
        return await self._get_data_api_endpoint(
            endpoint="/v1/positions",
            params=params,
            rate_limit_endpoint=PolymarketDataEndpoint.POSITIONS,
        )

    async def get_activity(
        self,
        params: ActivityParams,
    ) -> dict[str, Any] | list[Any]:
        return await self._get_data_api_endpoint(
            endpoint="/activity",
            params=params,
            rate_limit_endpoint=PolymarketDataEndpoint.POSITIONS,
        )

    async def get_trades(
        self,
        params: TradesParams,
    ) -> dict[str, Any] | list[Any]:
        return await self._get_data_api_endpoint(
            endpoint="/trades",
            params=params,
            rate_limit_endpoint=PolymarketDataEndpoint.TRADES,
        )

    async def get_leaderboard(
        self,
        params: LeaderboardParams = LeaderboardParams(),
    ) -> dict[str, Any] | list[Any]:
        return await self._get_data_api_endpoint(
            endpoint="/v1/leaderboard",
            params=params,
            rate_limit_endpoint=PolymarketDataEndpoint.LEADERBOARD,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def _get_data_api_endpoint(
        self,
        *,
        endpoint: str,
        params: BaseParams,
        rate_limit_endpoint: PolymarketDataEndpoint,
    ) -> dict[str, Any] | list[Any]:
        query_params = params.output_params()
        max_attempts = settings.polymarket.rate_limit_retry_attempts + 1

        for attempt in range(1, max_attempts + 1):
            try:
                await wait_for_data_api(rate_limit_endpoint)
                async with data_api_request_semaphore:
                    if settings.polymarket.request_delay_seconds:
                        await asyncio.sleep(settings.polymarket.request_delay_seconds)

                    return await self._client.get(
                        base_url=settings.polymarket.data_api,
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


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, HTTPStatusCodeError) and exc.status_code == 429
