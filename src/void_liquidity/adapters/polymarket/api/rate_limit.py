from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from weakref import WeakKeyDictionary

from asynciolimiter import StrictLimiter


DATA_API_REQUESTS_PER_SECOND = 80
TRADES_REQUESTS_PER_SECOND = 12
POSITIONS_REQUESTS_PER_SECOND = 8
LEADERBOARD_REQUESTS_PER_SECOND = 3


class PolymarketDataEndpoint(StrEnum):
    TRADES = "trades"
    POSITIONS = "positions"
    LEADERBOARD = "leaderboard"


class AsyncRateLimiter(Protocol):
    async def wait(self) -> None: ...


@dataclass(frozen=True)
class PolymarketDataApiLimiters:
    data_api: AsyncRateLimiter
    endpoints: dict[PolymarketDataEndpoint, AsyncRateLimiter]


limiter_sets: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    PolymarketDataApiLimiters,
] = WeakKeyDictionary()


async def wait_for_data_api(endpoint: PolymarketDataEndpoint) -> None:
    limiters = _get_limiters()

    await limiters.data_api.wait()
    await limiters.endpoints[endpoint].wait()


def _get_limiters() -> PolymarketDataApiLimiters:
    loop = asyncio.get_running_loop()
    limiters = limiter_sets.get(loop)
    if limiters is None:
        limiters = PolymarketDataApiLimiters(
            data_api=StrictLimiter(DATA_API_REQUESTS_PER_SECOND),
            endpoints={
                PolymarketDataEndpoint.TRADES: StrictLimiter(
                    TRADES_REQUESTS_PER_SECOND
                ),
                PolymarketDataEndpoint.POSITIONS: StrictLimiter(
                    POSITIONS_REQUESTS_PER_SECOND
                ),
                PolymarketDataEndpoint.LEADERBOARD: StrictLimiter(
                    LEADERBOARD_REQUESTS_PER_SECOND
                ),
            },
        )
        limiter_sets[loop] = limiters

    return limiters
