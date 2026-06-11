from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class WhalePosition(BaseModel):
    proxy_wallet: str
    token_id: str
    condition_id: str
    outcome: str
    outcome_index: int | None = None
    title: str = ""
    slug: str = ""
    size: float = 0.0
    current_value: float = 0.0
    avg_price: float = 0.0
    cur_price: float = 0.0
    opposite_token_id: str | None = None
    opposite_outcome: str | None = None
    end_date: date | None = None
    negative_risk: bool = False


class Market(BaseModel):
    token_id: str
    condition_id: str
    title: str
    slug: str
    outcome: str
    whale_count: int
    wallets: list[str] = Field(default_factory=list)
    total_size: float
    total_current_value: float
    weighted_avg_price: float
    cur_price: float
    opposite_token_id: str | None = None
    opposite_outcome: str | None = None
    end_date: date | None = None
    negative_risk: bool = False


class TrackedMarket(Market):
    run_id: str
    whales_run_id: str | None = None
    generated_at: datetime
    filter_profile: str


class TrackedMarkets(BaseModel):
    markets: list[TrackedMarket] = Field(default_factory=list)
    run_id: str
    whales_run_id: str | None = None
    generated_at: datetime
    filter_profile: str

    @property
    def market_count(self) -> int:
        return len(self.markets)


class MarketRunSummary(BaseModel):
    run_id: str
    whales_run_id: str | None = None
    generated_at: datetime
    checked_market_count: int


class MarketObservation(BaseModel):
    proxy_wallet: str
    token_id: str
    condition_id: str
    title: str
    slug: str
    outcome: str
    size: float = 0.0
    current_value: float = 0.0
    avg_price: float = 0.0
    cur_price: float = 0.0
    opposite_token_id: str | None = None
    opposite_outcome: str | None = None
    end_date: date | None = None
    negative_risk: bool = False
    generated_at: datetime


class MarketPositionCollectionError(BaseModel):
    proxy_wallet: str
    message: str


class Markets(BaseModel):
    positions: list[WhalePosition] = Field(default_factory=list)
    errors: list[MarketPositionCollectionError] = Field(default_factory=list)
    checked_market_count: int = 0
    generated_at: datetime


class MarketRunResult(BaseModel):
    run_id: str
    whales_run_id: str | None = None
    collected_markets: Markets
    tracked_markets: TrackedMarkets

    @property
    def errors(self) -> list[MarketPositionCollectionError]:
        return self.collected_markets.errors


class MarketTrackingResult(MarketRunResult):
    @property
    def markets(self) -> list[TrackedMarket]:
        return self.tracked_markets.markets
