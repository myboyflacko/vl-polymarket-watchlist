from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import StrEnum
from functools import lru_cache
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx
from asynciolimiter import StrictLimiter

from whale_tracker.providers.polymarket.errors import PolymarketRateLimitError
from whale_tracker.providers.polymarket.params.base import BaseParams
from whale_tracker.providers.polymarket.params.leaderboard.leaderboard import (
    LeaderboardParams,
)
from whale_tracker.providers.polymarket.params.orderbook import OrderBooksParams
from whale_tracker.providers.polymarket.params.profile.activity import ActivityParams
from whale_tracker.providers.polymarket.params.profile.closed_positions import (
    ClosedPositionsParams,
)
from whale_tracker.providers.polymarket.params.profile.current_positions import (
    CurrentPositionsParams,
)
from whale_tracker.providers.polymarket.params.profile.trades import TradesParams
from whale_tracker.settings import (
    PolymarketClobApiClientSettings,
    PolymarketDataApiClientSettings,
    get_settings,
)


class PolymarketDataEndpoint(StrEnum):
    TRADES = "trades"
    POSITIONS = "positions"
    LEADERBOARD = "leaderboard"
    ORDERBOOKS = "orderbooks"


class AsyncRateLimiter(Protocol):
    async def wait(self) -> None:
        ...


class PolymarketDataClient:
    def __init__(
        self,
        *,
        settings: PolymarketDataApiClientSettings | None = None,
        clob_settings: PolymarketClobApiClientSettings | None = None,
        async_client: httpx.AsyncClient | None = None,
        limiter_factory: Callable[[float], AsyncRateLimiter] = StrictLimiter,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.settings = settings or get_settings().polymarket_data_api_client
        self.clob_settings = clob_settings or get_settings().polymarket_clob_api_client
        self._client = async_client or httpx.AsyncClient(
            timeout=max(self.settings.timeout_seconds, self.clob_settings.timeout_seconds),
        )
        self._owns_client = async_client is None
        self._semaphore = semaphore or asyncio.Semaphore(
            self.settings.max_concurrent_requests,
        )
        self._data_api_limiter = limiter_factory(self.settings.requests_per_second)
        self._endpoint_limiters = {
            PolymarketDataEndpoint.TRADES: limiter_factory(
                self.settings.trades_requests_per_second,
            ),
            PolymarketDataEndpoint.POSITIONS: limiter_factory(
                self.settings.positions_requests_per_second,
            ),
            PolymarketDataEndpoint.LEADERBOARD: limiter_factory(
                self.settings.leaderboard_requests_per_second,
            ),
            PolymarketDataEndpoint.ORDERBOOKS: limiter_factory(
                self.clob_settings.orderbook_requests_per_second,
            ),
        }

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

    async def get_order_books(
        self,
        params: OrderBooksParams,
    ) -> dict[str, Any] | list[Any]:
        return await self._post_clob_endpoint(
            endpoint="/books",
            json=params.output_body(),
            rate_limit_endpoint=PolymarketDataEndpoint.ORDERBOOKS,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get_data_api_endpoint(
        self,
        *,
        endpoint: str,
        params: BaseParams,
        rate_limit_endpoint: PolymarketDataEndpoint,
    ) -> dict[str, Any] | list[Any]:
        query_params = params.output_params()
        max_attempts = self.settings.rate_limit_retry_attempts + 1
        url = urljoin(self.settings.base_url, endpoint)

        for attempt in range(1, max_attempts + 1):
            try:
                await self._wait_for_rate_limit(rate_limit_endpoint)
                async with self._semaphore:
                    if self.settings.request_delay_seconds:
                        await asyncio.sleep(self.settings.request_delay_seconds)

                    response = await self._client.get(
                        url=url,
                        params=query_params,
                    )
                    response.raise_for_status()
                    return response.json()

            except Exception as exc:
                is_rate_limited = _is_rate_limited(exc)

                if is_rate_limited and attempt < max_attempts:
                    wait_seconds = self.settings.rate_limit_backoff_seconds * attempt
                    await asyncio.sleep(wait_seconds)
                    continue

                if is_rate_limited:
                    raise PolymarketRateLimitError(
                        f"Rate limited for {endpoint} after {attempt} attempts"
                    ) from exc

                raise

        raise RuntimeError(f"Request attempts exhausted for {endpoint}")

    async def _post_clob_endpoint(
        self,
        *,
        endpoint: str,
        json: list[dict[str, Any]],
        rate_limit_endpoint: PolymarketDataEndpoint,
    ) -> dict[str, Any] | list[Any]:
        max_attempts = self.clob_settings.rate_limit_retry_attempts + 1
        url = urljoin(self.clob_settings.base_url, endpoint)

        for attempt in range(1, max_attempts + 1):
            try:
                await self._wait_for_rate_limit(rate_limit_endpoint)
                async with self._semaphore:
                    if self.clob_settings.request_delay_seconds:
                        await asyncio.sleep(self.clob_settings.request_delay_seconds)

                    response = await self._client.post(url=url, json=json)
                    response.raise_for_status()
                    return response.json()

            except Exception as exc:
                is_rate_limited = _is_rate_limited(exc)

                if is_rate_limited and attempt < max_attempts:
                    wait_seconds = self.clob_settings.rate_limit_backoff_seconds * attempt
                    await asyncio.sleep(wait_seconds)
                    continue

                if is_rate_limited:
                    raise PolymarketRateLimitError(
                        f"Rate limited for {endpoint} after {attempt} attempts"
                    ) from exc

                raise

        raise RuntimeError(f"Request attempts exhausted for {endpoint}")

    async def _wait_for_rate_limit(
        self,
        rate_limit_endpoint: PolymarketDataEndpoint,
    ) -> None:
        await self._data_api_limiter.wait()
        await self._endpoint_limiters[rate_limit_endpoint].wait()


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


@lru_cache(maxsize=1)
def get_polymarket_data_client() -> PolymarketDataClient:
    return PolymarketDataClient()
