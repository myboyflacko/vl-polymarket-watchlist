from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / '.env'


class PolymarketSettings(BaseSettings):
    data_api: str = "https://data-api.polymarket.com"
    gamma_api: str = "https://gamma-api.polymarket.com"
    max_concurrent_profile_requests: int = Field(
        default=4,
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

    polymarket_pk: str = Field(default="", alias="POLYMARKET_PK")
    polymarket_api_key: str = Field(default="", alias="POLYMARKET_API_KEY")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra="ignore",
    )


class Settings(BaseSettings):
    polymarket: PolymarketSettings = PolymarketSettings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
