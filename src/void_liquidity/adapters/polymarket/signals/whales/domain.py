from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from void_liquidity.adapters.polymarket.markets.whales.domain import MarketCandidate


MarketSignalProfileName = Literal[
    "confirmed",
    "pain",
    "high_value",
    "value_per_wallet",
]


class MarketSignalProfile(BaseModel):
    name: MarketSignalProfileName
    min_total_current_value: float = Field(default=0.0, ge=0)
    min_value_per_wallet: float = Field(default=0.0, ge=0)


class MarketSignal(BaseModel):
    profile: MarketSignalProfileName
    candidate: MarketCandidate
    score: float
    price_delta: float
    price_delta_pct: float | None
    value_per_wallet: float


class MarketSignalResult(BaseModel):
    profile: MarketSignalProfile
    signals: list[MarketSignal]
