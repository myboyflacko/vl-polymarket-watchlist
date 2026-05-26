import asyncio
from typing import Any

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


def test_get_trades_uses_trades_endpoint() -> None:
    client = FakeClient()

    asyncio.run(get_trades(client=client, params=TradesParams(user=WALLET)))

    assert client.calls[0]["endpoint"] == "/trades"
    assert client.calls[0]["params"]["user"] == WALLET
