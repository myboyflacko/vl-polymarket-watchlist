import asyncio
from typing import Any

import pytest

from void_liquidity.adapters.polymarket.api.endpoints.leaderboard import (
    get_leaderboard,
)
from void_liquidity.adapters.polymarket.api.endpoints.profile import (
    PolymarketRateLimitError,
    get_current_positions,
)
from void_liquidity.adapters.polymarket.api.client import HTTPStatusCodeError
from void_liquidity.adapters.polymarket.api.params import CurrentPositionsParams
from void_liquidity.adapters.polymarket.api.params.leaderboard import LeaderboardParams


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FailingClient:
    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        raise RuntimeError(f"boom for {endpoint}")


class RateLimitedClient:
    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        raise HTTPStatusCodeError(
            url=f"{base_url}{endpoint}",
            status_code=429,
            response_text="too many requests",
        )


def test_leaderboard_endpoint_propagates_client_errors() -> None:
    with pytest.raises(RuntimeError, match="boom for /v1/leaderboard"):
        asyncio.run(
            get_leaderboard(
                client=FailingClient(),
                params=LeaderboardParams(),
            )
        )


def test_profile_endpoint_translates_429_status_to_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from void_liquidity.adapters.polymarket.api.endpoints import profile

    monkeypatch.setattr(profile.settings.polymarket, "rate_limit_retry_attempts", 0)

    with pytest.raises(PolymarketRateLimitError):
        asyncio.run(
            get_current_positions(
                client=RateLimitedClient(),
                params=CurrentPositionsParams(user=WALLET),
            )
        )


def test_profile_endpoint_propagates_non_rate_limit_client_errors() -> None:
    with pytest.raises(RuntimeError, match="boom for /v1/positions"):
        asyncio.run(
            get_current_positions(
                client=FailingClient(),
                params=CurrentPositionsParams(user=WALLET),
            )
        )
