from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    categories: list[WhaleQualifiedMarketProfileName]
    category_scores: dict[WhaleQualifiedMarketProfileName, float] = Field(
        default_factory=dict
    )
    candidate: MarketCandidate
    score: float
    price_delta: float
    price_delta_pct: float | None
    value_per_wallet: float

    @model_validator(mode="before")
    @classmethod
    def _profile_to_categories(cls, data):
        if isinstance(data, dict) and "profile" in data and "categories" not in data:
            profile = data["profile"]
            data = dict(data)
            data["categories"] = [profile]
            data.setdefault("category_scores", {profile: data.get("score", 0.0)})
        return data

    @property
    def profile(self) -> WhaleQualifiedMarketProfileName:
        return self.categories[0]


class QualifiedMarketResult(BaseModel):
    profiles: list[WhaleQualifiedMarketProfile] = Field(default_factory=list)
    qualified_markets: list[QualifiedMarket]

    @property
    def profile(self) -> WhaleQualifiedMarketProfile:
        if self.profiles:
            return self.profiles[0]

        return WhaleQualifiedMarketProfile(name="high_value")
