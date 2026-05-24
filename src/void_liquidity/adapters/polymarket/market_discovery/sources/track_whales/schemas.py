from pydantic import BaseModel, Field


class CandidatePoolConfig(BaseModel):
    category: str = "OVERALL"
    time_period: str = "MONTH"
    top_n: int = Field(default=250, ge=1)
    leaderboard_limit: int = Field(default=50, ge=1, le=50)


class CurrentPositionsConfig(BaseModel):
    limit: int = Field(default=500, ge=1, le=500)
    sort_by: str = "CURRENT"
    sort_direction: str = "DESC"


class ClosedPositionsConfig(BaseModel):
    window_days: int = Field(default=30, ge=1)
    limit: int = Field(default=50, ge=1, le=50)
    sort_by: str = "TIMESTAMP"
    sort_direction: str = "DESC"
    max_positions_per_wallet: int = Field(default=500, ge=1)


class ActivityConfig(BaseModel):
    trade_count_window_days: int = Field(default=30, ge=1)
    min_trade_count: int = Field(default=10, ge=0)
    last_activity_max_age_days: int = Field(default=7, ge=1)
    limit: int = Field(default=500, ge=1, le=500)
    sort_by: str = "TIMESTAMP"
    sort_direction: str = "DESC"
    type: list[str] = Field(default_factory=lambda: ["TRADE"])


class WhaleFilterConfig(BaseModel):
    min_current_position_value: float = Field(default=10_000.0, ge=0)
    min_closed_trade_count: int = Field(default=50, ge=1)
    min_closed_positions_pnl: float = 0.0
    min_roi: float = 0.0
    min_profit_factor: float = Field(default=1.5, ge=0)
    min_activity_volume: float = Field(default=10_000.0, ge=0)
    max_largest_win_share: float = Field(default=0.60, ge=0, le=1)


class WhaleTrackingProfile(BaseModel):
    profile_version: str = "whale_tracking_v2"
    target_wallet_count: int = Field(default=50, ge=1)
    wallet_batch_size: int = Field(default=4, ge=1)
    output_path: str = (
        "src/void_liquidity/data/reports/track_whales/"
        "polymarket_whales.json"
    )
    candidate_pool: CandidatePoolConfig = Field(default_factory=CandidatePoolConfig)
    current_positions: CurrentPositionsConfig = Field(
        default_factory=CurrentPositionsConfig,
    )
    closed_positions: ClosedPositionsConfig = Field(
        default_factory=ClosedPositionsConfig,
    )
    activity: ActivityConfig = Field(default_factory=ActivityConfig)
    filters: WhaleFilterConfig = Field(default_factory=WhaleFilterConfig)
