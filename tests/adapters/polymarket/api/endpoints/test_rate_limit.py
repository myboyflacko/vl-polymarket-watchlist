import asyncio
from typing import Any

import pytest

from void_liquidity.adapters.polymarket.api.endpoints import leaderboard, profile
from void_liquidity.adapters.polymarket.api.params import CurrentPositionsParams, TradesParams
from void_liquidity.adapters.polymarket.api.params.leaderboard import LeaderboardParams
from void_liquidity.adapters.polymarket.api.rate_limit import PolymarketDataEndpoint


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FakeClient:
    async def get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        return []


def test_get_trades_waits_for_trades_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoints: list[PolymarketDataEndpoint] = []

    async def fake_wait(endpoint: PolymarketDataEndpoint) -> None:
        endpoints.append(endpoint)

    monkeypatch.setattr(profile, "wait_for_data_api", fake_wait)

    asyncio.run(profile.get_trades(client=FakeClient(), params=TradesParams(user=WALLET)))

    assert endpoints == [PolymarketDataEndpoint.TRADES]


def test_get_current_positions_waits_for_positions_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoints: list[PolymarketDataEndpoint] = []

    async def fake_wait(endpoint: PolymarketDataEndpoint) -> None:
        endpoints.append(endpoint)

    monkeypatch.setattr(profile, "wait_for_data_api", fake_wait)

    asyncio.run(
        profile.get_current_positions(
            client=FakeClient(),
            params=CurrentPositionsParams(user=WALLET),
        )
    )

    assert endpoints == [PolymarketDataEndpoint.POSITIONS]


def test_get_leaderboard_waits_for_leaderboard_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoints: list[PolymarketDataEndpoint] = []

    async def fake_wait(endpoint: PolymarketDataEndpoint) -> None:
        endpoints.append(endpoint)

    monkeypatch.setattr(leaderboard, "wait_for_data_api", fake_wait)

    asyncio.run(
        leaderboard.get_leaderboard(
            client=FakeClient(),
            params=LeaderboardParams(),
        )
    )

    assert endpoints == [PolymarketDataEndpoint.LEADERBOARD]
