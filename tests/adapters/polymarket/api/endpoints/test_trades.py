import asyncio
from typing import Any

import pytest

from void_liquidity.adapters.polymarket.api.endpoints.profile import get_trades
from void_liquidity.adapters.polymarket.api.params import TradesParams


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class UnusedClient:
    pass


class RecordingDataClient:
    def __init__(self) -> None:
        self.params: list[Any] = []

    async def get_trades(self, params: TradesParams) -> list[Any]:
        self.params.append(params)
        return []


def test_get_trades_delegates_to_data_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from void_liquidity.adapters.polymarket.api.endpoints import profile

    data_client = RecordingDataClient()
    monkeypatch.setattr(
        profile,
        "get_polymarket_data_client",
        lambda: data_client,
    )

    asyncio.run(get_trades(client=UnusedClient(), params=TradesParams(user=WALLET)))

    assert data_client.params[0].user == WALLET
