import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from void_liquidity.adapters.polymarket.api import client as client_module
from void_liquidity.adapters.polymarket.api.client import (
    PolymarketDataClient,
    get_polymarket_data_client,
)
from void_liquidity.adapters.polymarket.api.errors import PolymarketRateLimitError
from void_liquidity.adapters.polymarket.api.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    LeaderboardParams,
    TradesParams,
)
from void_liquidity.settings import PolymarketDataApiClientSettings


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FakeAsyncClient:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict[str, Any]] = []
        self.close_count = 0

    async def get(
        self,
        *,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self.calls.append({"url": url, "params": params})
        return httpx.Response(
            self.status_code,
            json=[],
            request=httpx.Request("GET", url),
        )

    async def aclose(self) -> None:
        self.close_count += 1


class FailingAsyncClient(FakeAsyncClient):
    async def get(
        self,
        *,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self.calls.append({"url": url, "params": params})
        raise RuntimeError(f"boom for {url}")


class RecordingLimiter:
    def __init__(self, rate: float, waits: list[float]) -> None:
        self.rate = rate
        self.waits = waits

    async def wait(self) -> None:
        self.waits.append(self.rate)


class RecordingSemaphore:
    def __init__(self) -> None:
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self) -> None:
        self.enter_count += 1

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.exit_count += 1


def _settings(**overrides: Any) -> PolymarketDataApiClientSettings:
    payload = {
        "base_url": "https://data-api.example.test",
        "timeout_seconds": 10.0,
        "max_concurrent_requests": 4,
        "request_delay_seconds": 0,
        "rate_limit_retry_attempts": 0,
        "rate_limit_backoff_seconds": 0,
        "requests_per_second": 80,
        "trades_requests_per_second": 12,
        "positions_requests_per_second": 8,
        "leaderboard_requests_per_second": 3,
    }
    payload.update(overrides)
    return PolymarketDataApiClientSettings(**payload)


def _limiter_factory(waits: list[float]) -> Callable[[float], RecordingLimiter]:
    return lambda rate: RecordingLimiter(rate, waits)


@pytest.mark.parametrize(
    ("method", "params", "expected_endpoint", "expected_endpoint_rate"),
    [
        (
            PolymarketDataClient.get_trades,
            TradesParams(user=WALLET),
            "/trades",
            12,
        ),
        (
            PolymarketDataClient.get_current_positions,
            CurrentPositionsParams(user=WALLET),
            "/v1/positions",
            8,
        ),
        (
            PolymarketDataClient.get_closed_positions,
            ClosedPositionsParams(user=WALLET),
            "/v1/closed-positions",
            8,
        ),
        (
            PolymarketDataClient.get_activity,
            ActivityParams(user=WALLET),
            "/activity",
            8,
        ),
        (
            PolymarketDataClient.get_leaderboard,
            LeaderboardParams(),
            "/v1/leaderboard",
            3,
        ),
    ],
)
def test_data_client_methods_use_expected_endpoint_and_limiters(
    method: Callable[[PolymarketDataClient, Any], Awaitable[Any]],
    params: Any,
    expected_endpoint: str,
    expected_endpoint_rate: float,
) -> None:
    waits: list[float] = []
    async_client = FakeAsyncClient()
    client = PolymarketDataClient(
        settings=_settings(),
        async_client=async_client,
        limiter_factory=_limiter_factory(waits),
    )

    asyncio.run(method(client, params))

    assert async_client.calls[0]["url"] == (
        f"https://data-api.example.test{expected_endpoint}"
    )
    assert waits == [80, expected_endpoint_rate]


def test_data_client_uses_semaphore_and_request_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    semaphore = RecordingSemaphore()

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    client = PolymarketDataClient(
        settings=_settings(request_delay_seconds=0.25),
        async_client=FakeAsyncClient(),
        limiter_factory=_limiter_factory([]),
        semaphore=semaphore,
    )

    asyncio.run(client.get_trades(TradesParams(user=WALLET)))

    assert sleeps == [0.25]
    assert semaphore.enter_count == 1
    assert semaphore.exit_count == 1


def test_data_client_translates_429_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    async_client = FakeAsyncClient(status_code=429)
    client = PolymarketDataClient(
        settings=_settings(rate_limit_retry_attempts=1),
        async_client=async_client,
        limiter_factory=_limiter_factory([]),
    )

    with pytest.raises(PolymarketRateLimitError):
        asyncio.run(client.get_trades(TradesParams(user=WALLET)))

    assert len(async_client.calls) == 2


def test_data_client_propagates_non_rate_limit_errors() -> None:
    client = PolymarketDataClient(
        settings=_settings(),
        async_client=FailingAsyncClient(),
        limiter_factory=_limiter_factory([]),
    )

    with pytest.raises(
        RuntimeError, match="boom for https://data-api.example.test/trades"
    ):
        asyncio.run(client.get_trades(TradesParams(user=WALLET)))


def test_data_client_close_closes_owned_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_async_client = FakeAsyncClient()
    monkeypatch.setattr(
        client_module.httpx, "AsyncClient", lambda timeout: fake_async_client
    )

    client = PolymarketDataClient(settings=_settings())

    asyncio.run(client.close())

    assert fake_async_client.close_count == 1


def test_data_client_close_keeps_injected_async_client_open() -> None:
    fake_async_client = FakeAsyncClient()
    client = PolymarketDataClient(settings=_settings(), async_client=fake_async_client)

    asyncio.run(client.close())

    assert fake_async_client.close_count == 0


def test_get_polymarket_data_client_returns_cached_instance() -> None:
    get_polymarket_data_client.cache_clear()

    first = get_polymarket_data_client()
    second = get_polymarket_data_client()

    assert first is second

    asyncio.run(first.close())
    get_polymarket_data_client.cache_clear()
