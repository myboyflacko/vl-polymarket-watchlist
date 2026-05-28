import asyncio
from typing import Any

import pytest

from void_liquidity.adapters.polymarket.api.endpoints import profile
from void_liquidity.adapters.polymarket.api.endpoints.profile import get_trades
from void_liquidity.adapters.polymarket.api.params import TradesParams


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(
        self,
        *,
        base_url: str,
        endpoint: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "base_url": base_url,
                "endpoint": endpoint,
                "params": params,
            }
        )
        return []


def test_get_trades_uses_trades_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_wait_for_data_api(endpoint: Any) -> None:
        return None

    monkeypatch.setattr(profile, "wait_for_data_api", fake_wait_for_data_api)
    monkeypatch.setattr(profile.settings.polymarket, "request_delay_seconds", 0)

    client = FakeClient()

    asyncio.run(get_trades(client=client, params=TradesParams(user=WALLET)))

    assert client.calls[0]["endpoint"] == "/trades"
    assert client.calls[0]["params"]["user"] == WALLET
