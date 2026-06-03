from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data/db/whale_tracker.sqlite3"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"


class PolymarketDataApiClientSettings(BaseSettings):
    base_url: str = Field(
        default="https://data-api.polymarket.com",
        alias="POLYMARKET_DATA_API_BASE_URL",
    )
    timeout_seconds: float = Field(
        default=10.0,
        ge=0,
        alias="POLYMARKET_DATA_API_TIMEOUT_SECONDS",
    )
    max_concurrent_requests: int = Field(
        default=4,
        ge=1,
        alias="POLYMARKET_DATA_API_MAX_CONCURRENT_REQUESTS",
    )
    request_delay_seconds: float = Field(
        default=0,
        ge=0,
        alias="POLYMARKET_DATA_API_REQUEST_DELAY_SECONDS",
    )
    rate_limit_retry_attempts: int = Field(
        default=5,
        ge=0,
        alias="POLYMARKET_DATA_API_RATE_LIMIT_RETRY_ATTEMPTS",
    )
    rate_limit_backoff_seconds: float = Field(
        default=60.0,
        ge=0,
        alias="POLYMARKET_DATA_API_RATE_LIMIT_BACKOFF_SECONDS",
    )
    requests_per_second: float = Field(
        default=80,
        gt=0,
        alias="POLYMARKET_DATA_API_REQUESTS_PER_SECOND",
    )
    trades_requests_per_second: float = Field(
        default=12,
        gt=0,
        alias="POLYMARKET_TRADES_REQUESTS_PER_SECOND",
    )
    positions_requests_per_second: float = Field(
        default=8,
        gt=0,
        alias="POLYMARKET_POSITIONS_REQUESTS_PER_SECOND",
    )
    leaderboard_requests_per_second: float = Field(
        default=3,
        gt=0,
        alias="POLYMARKET_LEADERBOARD_REQUESTS_PER_SECOND",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


class DatabaseSettings(BaseSettings):
    sqlite_path: Path = Field(
        default=DEFAULT_SQLITE_PATH,
        alias="WHALE_TRACKER_SQLITE_PATH",
    )
    url: str | None = Field(default=None, alias="WHALE_TRACKER_DATABASE_URL")

    @property
    def database_url(self) -> str:
        if self.url:
            return self.url

        return f"sqlite:///{self.sqlite_path}"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class LoggingSettings(BaseSettings):
    log_dir: Path = Field(default=DEFAULT_LOG_DIR, alias="WHALE_TRACKER_LOG_DIR")
    level: str = Field(default="INFO", alias="WHALE_TRACKER_LOG_LEVEL")
    retention_days: int = Field(
        default=14,
        ge=0,
        alias="WHALE_TRACKER_LOG_RETENTION_DAYS",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseSettings):
    polymarket_data_api_client: PolymarketDataApiClientSettings = Field(
        default_factory=PolymarketDataApiClientSettings,
    )
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
