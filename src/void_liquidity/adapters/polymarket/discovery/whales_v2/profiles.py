from typing import Literal

from pydantic import BaseModel, Field


class TradeFirstRankingProfile(BaseModel):
    pnl_weight: float = Field(default=0.30, ge=0)
    volume_weight: float = Field(default=0.25, ge=0)
    trade_activity_weight: float = Field(default=0.20, ge=0)
    recency_weight: float = Field(default=0.15, ge=0)
    exposure_weight: float = Field(default=0.10, ge=0)
    concentration_penalty_weight: float = Field(default=0.10, ge=0)
    bottom_cut_percentile: float = Field(default=0.25, ge=0, le=1)


class WhaleTrackerV2Profile(BaseModel):
    profile_version: str = "whale_tracking_v2_trade_first"
    wallet_count: int = Field(default=250, ge=1)
    wallet_batch_size: int = Field(default=4, ge=1)
    leaderboard_category: Literal[
        "OVERALL",
        "POLITICS",
        "SPORTS",
        "CRYPTO",
        "CULTURE",
        "MENTIONS",
        "WEATHER",
        "ECONOMICS",
        "TECH",
        "FINANCE",
    ] = "OVERALL"
    leaderboard_time_period: Literal["DAY", "WEEK", "MONTH", "ALL"] = "MONTH"
    leaderboard_limit: int = Field(default=50, ge=1, le=50)
    trade_window_days: int = Field(default=30, ge=1)
    recent_window_days: int = Field(default=7, ge=1)
    trade_limit: int = Field(default=500, ge=1, le=10_000)
    max_trade_pages_per_wallet: int = Field(default=20, ge=1)
    taker_only: bool = True
    current_positions_limit: int = Field(default=500, ge=1, le=500)
    ranking: TradeFirstRankingProfile = Field(default_factory=TradeFirstRankingProfile)
