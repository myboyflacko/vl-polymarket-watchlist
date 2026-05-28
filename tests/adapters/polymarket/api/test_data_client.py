import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from void_liquidity.adapters.polymarket.api import data_client
from void_liquidity.adapters.polymarket.api.client import HTTPStatusCodeError
from void_liquidity.adapters.polymarket.api.data_client import PolymarketDataClient
from void_liquidity.adapters.polymarket.api.errors import PolymarketRateLimitError
from void_liquidity.adapters.polymarket.api.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    LeaderboardParams,
    TradesParams,
)
from void_liquidity.adapters.polymarket.api.rate_limit import PolymarketDataEndpoint


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FakeHTTPClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.close_count = 0

    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        self.calls.append(
            {
                "base_url": base_url,
                "endpoint": endpoint,
                "params": params,
            }
        )
        return []

    async def close(self) -> None:
        self.close_count += 1


class RateLimitedHTTPClient(FakeHTTPClient):
    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        self.calls.append({"base_url": base_url, "endpoint": endpoint, "params": params})
        raise HTTPStatusCodeError(
            url=f"{base_url}{endpoint}",
            status_code=429,
            response_text="too many requests",
        )


class FailingHTTPClient(FakeHTTPClient):
    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        self.calls.append({"base_url": base_url, "endpoint": endpoint, "params": params})
        raise RuntimeError(f"boom for {endpoint}")


class RecordingSemaphore:
    def __init__(self) -> None:
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self) -> None:
        self.enter_count += 1

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.exit_count += 1


def _disable_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data_client.settings.polymarket, "request_delay_seconds", 0)


def _disable_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data_client.settings.polymarket, "rate_limit_retry_attempts", 0)


@pytest.mark.parametrize(
    ("method", "params", "expected_endpoint", "expected_limiter"),
    [
        (
            PolymarketDataClient.get_trades,
            TradesParams(user=WALLET),
            "/trades",
            PolymarketDataEndpoint.TRADES,
        ),
        (
            PolymarketDataClient.get_current_positions,
            CurrentPositionsParams(user=WALLET),
            "/v1/positions",
            PolymarketDataEndpoint.POSITIONS,
        ),
        (
            PolymarketDataClient.get_closed_positions,
            ClosedPositionsParams(user=WALLET),
            "/v1/closed-positions",
            PolymarketDataEndpoint.POSITIONS,
        ),
        (
            PolymarketDataClient.get_activity,
            ActivityParams(user=WALLET),
            "/activity",
            PolymarketDataEndpoint.POSITIONS,
        ),
        (
            PolymarketDataClient.get_leaderboard,
            LeaderboardParams(),
            "/v1/leaderboard",
            PolymarketDataEndpoint.LEADERBOARD,
        ),
    ],
)
def test_data_client_methods_use_expected_endpoint_and_limiter(
    monkeypatch: pytest.MonkeyPatch,
    method: Callable[[PolymarketDataClient, Any], Awaitable[Any]],
    params: Any,
    expected_endpoint: str,
    expected_limiter: PolymarketDataEndpoint,
) -> None:
    _disable_delay(monkeypatch)
    endpoints: list[PolymarketDataEndpoint] = []

    async def fake_wait_for_data_api(endpoint: PolymarketDataEndpoint) -> None:
        endpoints.append(endpoint)

    monkeypatch.setattr(data_client, "wait_for_data_api", fake_wait_for_data_api)

    http_client = FakeHTTPClient()
    client = PolymarketDataClient(http_client=http_client)

    asyncio.run(method(client, params))

    assert endpoints == [expected_limiter]
    assert http_client.calls[0]["endpoint"] == expected_endpoint


def test_data_client_uses_semaphore_and_request_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    semaphore = RecordingSemaphore()

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def fake_wait_for_data_api(endpoint: PolymarketDataEndpoint) -> None:
        return None

    monkeypatch.setattr(data_client.settings.polymarket, "request_delay_seconds", 0.25)
    monkeypatch.setattr(data_client.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(data_client, "wait_for_data_api", fake_wait_for_data_api)
    monkeypatch.setattr(data_client, "data_api_request_semaphore", semaphore)

    client = PolymarketDataClient(http_client=FakeHTTPClient())

    asyncio.run(client.get_trades(TradesParams(user=WALLET)))

    assert sleeps == [0.25]
    assert semaphore.enter_count == 1
    assert semaphore.exit_count == 1


def test_data_client_translates_429_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_delay(monkeypatch)
    monkeypatch.setattr(data_client.settings.polymarket, "rate_limit_retry_attempts", 1)
    monkeypatch.setattr(data_client.settings.polymarket, "rate_limit_backoff_seconds", 0)

    async def fake_wait_for_data_api(endpoint: PolymarketDataEndpoint) -> None:
        return None

    monkeypatch.setattr(data_client, "wait_for_data_api", fake_wait_for_data_api)

    http_client = RateLimitedHTTPClient()
    client = PolymarketDataClient(http_client=http_client)

    with pytest.raises(PolymarketRateLimitError):
        asyncio.run(client.get_trades(TradesParams(user=WALLET)))

    assert len(http_client.calls) == 2


def test_data_client_propagates_non_rate_limit_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_delay(monkeypatch)
    _disable_retries(monkeypatch)

    async def fake_wait_for_data_api(endpoint: PolymarketDataEndpoint) -> None:
        return None

    monkeypatch.setattr(data_client, "wait_for_data_api", fake_wait_for_data_api)

    client = PolymarketDataClient(http_client=FailingHTTPClient())

    with pytest.raises(RuntimeError, match="boom for /trades"):
        asyncio.run(client.get_trades(TradesParams(user=WALLET)))


def test_data_client_close_closes_owned_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_http_client = FakeHTTPClient()
    monkeypatch.setattr(data_client, "HTTPClient", lambda: fake_http_client)

    client = PolymarketDataClient()

    asyncio.run(client.close())

    assert fake_http_client.close_count == 1


def test_data_client_close_keeps_injected_http_client_open() -> None:
    fake_http_client = FakeHTTPClient()
    client = PolymarketDataClient(http_client=fake_http_client)

    asyncio.run(client.close())

    assert fake_http_client.close_count == 0
