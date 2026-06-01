from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import MarketCandidate


WhaleQualifiedMarketProfileName = Literal[
    "confirmed",
    "pain",
    "high_value",
    "value_per_wallet",
]


class WhaleQualifiedMarketProfile(BaseModel):
    name: WhaleQualifiedMarketProfileName
    min_total_current_value: float = Field(default=0.0, ge=0)
    min_value_per_wallet: float = Field(default=0.0, ge=0)


class QualifiedMarket(BaseModel):
    profile: WhaleQualifiedMarketProfileName
    candidate: MarketCandidate
    score: float
    price_delta: float
    price_delta_pct: float | None
    value_per_wallet: float


class QualifiedMarketResult(BaseModel):
    profiles: list[WhaleQualifiedMarketProfile] = Field(default_factory=list)
    qualified_markets: list[QualifiedMarket]

    @property
    def profile(self) -> WhaleQualifiedMarketProfile:
        if self.profiles:
            return self.profiles[0]

        return WhaleQualifiedMarketProfile(name="high_value")
