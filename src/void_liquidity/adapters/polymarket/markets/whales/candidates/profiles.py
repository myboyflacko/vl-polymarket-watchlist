from __future__ import annotations

from pydantic import BaseModel, Field

from void_liquidity.adapters.polymarket.markets.whales.candidates.service import (
    DEFAULT_MIN_WHALE_COUNT,
)


class WhaleMarketCandidateProfile(BaseModel):
    min_whale_count: int = Field(default=DEFAULT_MIN_WHALE_COUNT, ge=1)
