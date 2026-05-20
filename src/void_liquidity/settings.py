from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / '.env'


class PolymarketSettings(BaseSettings):
    data_api: str = "https://data-api.polymarket.com"
    gamma_api: str = "https://gamma-api.polymarket.com"
    max_concurrent_profile_requests: int = Field(
        default=2,
        ge=1,
        alias="MAX_CONCURRENT_PROFILE_REQUESTS",
    )
    request_delay_seconds: float = Field(
        default=0.5,
        ge=0,
        alias="POLYMARKET_REQUEST_DELAY_SECONDS",
    )
    rate_limit_retry_attempts: int = Field(
        default=5,
        ge=0,
        alias="POLYMARKET_RATE_LIMIT_RETRY_ATTEMPTS",
    )
    rate_limit_backoff_seconds: float = Field(
        default=60.0,
        ge=0,
        alias="POLYMARKET_RATE_LIMIT_BACKOFF_SECONDS",
    )

    polymarket_pk: str = Field(alias="POLYMARKET_PK")
    polymarket_api_key: str = Field(alias="POLYMARKET_API_KEY")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra="ignore",
    )


class WhaleTrackerSettings(BaseSettings):
    target_count: int = Field(default=50, ge=1, alias="WHALE_TARGET_COUNT")
    lookback_days: int = Field(default=30, ge=1, alias="WHALE_LOOKBACK_DAYS")
    min_trade_count: int = Field(default=50, ge=1, alias="WHALE_MIN_TRADE_COUNT")
    min_win_rate: float = Field(
        default=0.70,
        ge=0,
        le=1,
        alias="WHALE_MIN_WIN_RATE",
    )
    min_leaderboard_volume: float = Field(
        default=100_000.0,
        ge=0,
        alias="WHALE_MIN_LEADERBOARD_VOLUME",
    )
    min_current_position_value: float = Field(
        default=10_000.0,
        ge=0,
        alias="WHALE_MIN_CURRENT_POSITION_VALUE",
    )
    max_closed_positions_per_wallet: int = Field(
        default=500,
        ge=1,
        alias="WHALE_MAX_CLOSED_POSITIONS_PER_WALLET",
    )
    batch_size: int = Field(default=4, ge=1, alias="WHALE_BATCH_SIZE")
    output_path: str = Field(
        default="data/polymarket_whales.json",
        alias="WHALE_OUTPUT_PATH",
    )

    leaderboard_time_period: str = Field(
        default="MONTH",
        alias="WHALE_LEADERBOARD_TIME_PERIOD",
    )
    leaderboard_order_by: str = Field(
        default="PNL",
        alias="WHALE_LEADERBOARD_ORDER_BY",
    )
    leaderboard_limit: int = Field(
        default=50,
        ge=1,
        alias="WHALE_LEADERBOARD_LIMIT",
    )

    closed_positions_limit: int = Field(
        default=50,
        ge=1,
        alias="WHALE_CLOSED_POSITIONS_LIMIT",
    )
    closed_positions_sort_by: str = Field(
        default="TIMESTAMP",
        alias="WHALE_CLOSED_POSITIONS_SORT_BY",
    )
    closed_positions_sort_direction: str = Field(
        default="DESC",
        alias="WHALE_CLOSED_POSITIONS_SORT_DIRECTION",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra="ignore",
    )


class Settings(BaseSettings):
    polymarket: PolymarketSettings = PolymarketSettings()
    whale_tracker: WhaleTrackerSettings = WhaleTrackerSettings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
