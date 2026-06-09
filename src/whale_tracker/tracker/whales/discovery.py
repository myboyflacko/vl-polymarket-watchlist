from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WhaleDiscoveryProfile(BaseModel):
    profile_version: str = "whale_leaderboard_only_v1"
    wallet_count: int = Field(default=50, ge=1)
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
    current_positions_market_chunk_size: int = Field(default=50, ge=1, le=100)
