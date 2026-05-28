import asyncio
from typing import Any

import pytest

from void_liquidity.adapters.polymarket.api.endpoints.leaderboard import (
    get_leaderboard,
)
from void_liquidity.adapters.polymarket.api.endpoints.profile import (
    get_current_positions,
)
from void_liquidity.adapters.polymarket.api.params import CurrentPositionsParams
from void_liquidity.adapters.polymarket.api.params.leaderboard import LeaderboardParams


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class UnusedClient:
    pass


class FailingDataClient:
    async def get_leaderboard(self, params: Any) -> list[Any]:
        raise RuntimeError("boom for /v1/leaderboard")

    async def get_current_positions(self, params: Any) -> list[Any]:
        raise RuntimeError("boom for /v1/positions")


def test_leaderboard_endpoint_propagates_data_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from void_liquidity.adapters.polymarket.api.endpoints import leaderboard

    monkeypatch.setattr(
        leaderboard,
        "get_polymarket_data_client",
        lambda: FailingDataClient(),
    )

    with pytest.raises(RuntimeError, match="boom for /v1/leaderboard"):
        asyncio.run(
            get_leaderboard(
                client=UnusedClient(),
                params=LeaderboardParams(),
            )
        )


def test_profile_endpoint_propagates_data_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from void_liquidity.adapters.polymarket.api.endpoints import profile

    monkeypatch.setattr(
        profile,
        "get_polymarket_data_client",
        lambda: FailingDataClient(),
    )

    with pytest.raises(RuntimeError, match="boom for /v1/positions"):
        asyncio.run(
            get_current_positions(
                client=UnusedClient(),
                params=CurrentPositionsParams(user=WALLET),
            )
        )
