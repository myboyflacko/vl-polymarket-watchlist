from __future__ import annotations

from pydantic import BaseModel, Field

from whale_tracker.tracker.markets.domain import QualifiedMarketProfileName


class MarketFilterProfile(BaseModel):
    name: str = "default_market_filter"
    min_whale_count: int = Field(default=3, ge=1)


class MarketScoringProfile(BaseModel):
    name: QualifiedMarketProfileName
    min_total_current_value: float = Field(default=0.0, ge=0)
    min_value_per_wallet: float = Field(default=0.0, ge=0)


MarketCandidateProfile = MarketFilterProfile
QualifiedMarketProfile = MarketScoringProfile


class MarketTrackingProfile(BaseModel):
    filter: MarketFilterProfile = Field(default_factory=MarketFilterProfile)
    scoring: tuple[MarketScoringProfile, ...] = Field(
        default_factory=lambda: (
            MarketScoringProfile(name="confirmed"),
            MarketScoringProfile(name="pain"),
            MarketScoringProfile(name="high_value"),
            MarketScoringProfile(name="value_per_wallet"),
        )
    )

    @property
    def candidate(self) -> MarketFilterProfile:
        return self.filter

    @property
    def qualified_profiles(self) -> tuple[MarketScoringProfile, ...]:
        return self.scoring
