import asyncio

from void_liquidity.adapters.polymarket.api import rate_limit
from void_liquidity.adapters.polymarket.api.rate_limit import (
    PolymarketDataApiLimiters,
    PolymarketDataEndpoint,
)


class RecordingLimiter:
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self.calls = calls

    async def wait(self) -> None:
        self.calls.append(self.name)


def test_wait_for_data_api_uses_global_and_endpoint_limiter(
    monkeypatch,
) -> None:
    calls: list[str] = []
    limiters = PolymarketDataApiLimiters(
        data_api=RecordingLimiter("data_api", calls),
        endpoints={
            PolymarketDataEndpoint.TRADES: RecordingLimiter("trades", calls),
        },
    )
    monkeypatch.setattr(
        rate_limit,
        "_get_limiters",
        lambda: limiters,
    )

    asyncio.run(rate_limit.wait_for_data_api(PolymarketDataEndpoint.TRADES))

    assert calls == ["data_api", "trades"]
