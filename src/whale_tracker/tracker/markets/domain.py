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
    qualified: bool = False
    categories: list[str] = Field(default_factory=list)
    category_scores: dict[str, float] = Field(default_factory=dict)
    score: float = 0.0
    price_delta: float = 0.0
    price_delta_pct: float | None = None
    value_per_wallet: float = 0.0


class MarketRunSummary(BaseModel):
    run_id: str
    whales_run_id: str | None = None
    generated_at: datetime
    checked_market_count: int
    filtered_market_count: int
    scored_market_count: int
    removed_market_count: int
    limit: int | None = None

    @property
    def selection_run_id(self) -> str | None:
        return self.whales_run_id


class MarketSnapshot(Market):
    run_id: str
    generated_at: datetime


class MarketPositionCollectionError(BaseModel):
    proxy_wallet: str
    message: str


class Markets(BaseModel):
    positions: list[WhalePosition] = Field(default_factory=list)
    errors: list[MarketPositionCollectionError] = Field(default_factory=list)
    checked_market_count: int = 0
    generated_at: datetime


class FilteredMarkets(BaseModel):
    markets: list[Market] = Field(default_factory=list)
    removed_markets: list[Market] = Field(default_factory=list)
    checked_market_count: int
    generated_at: datetime
    profile_name: str

    @property
    def market_count(self) -> int:
        return len(self.markets)

    @property
    def removed_market_count(self) -> int:
        return len(self.removed_markets)


class ScoredMarket(BaseModel):
    market: Market
    score: float


class ScoredMarkets(BaseModel):
    markets: list[ScoredMarket] = Field(default_factory=list)
    removed_markets: list[ScoredMarket] = Field(default_factory=list)
    generated_at: datetime
    profile_name: str

    @property
    def market_count(self) -> int:
        return len(self.markets)

    @property
    def removed_market_count(self) -> int:
        return len(self.removed_markets)

    @property
    def selected_markets(self) -> list[Market]:
        return [scored.market for scored in self.markets]


class MarketRunResult(BaseModel):
    run_id: str
    whales_run_id: str | None = None
    collected_markets: Markets
    filtered_markets: FilteredMarkets
    scored_markets: ScoredMarkets | None = None
    limit: int | None = None

    @property
    def result_markets(self) -> FilteredMarkets | ScoredMarkets:
        return self.scored_markets or self.filtered_markets

    @property
    def positions(self) -> list[WhalePosition]:
        return self.collected_markets.positions

    @property
    def errors(self) -> list[MarketPositionCollectionError]:
        return self.collected_markets.errors

    @property
    def selected_markets(self) -> list[Market]:
        if self.scored_markets is not None:
            return self.scored_markets.selected_markets
        return self.filtered_markets.markets


class MarketTrackingResult(MarketRunResult):
    @property
    def selection_run_id(self) -> str | None:
        return self.whales_run_id

    @property
    def markets(self) -> list[Market]:
        return self.filtered_markets.markets

    @property
    def qualified_markets(self) -> list[Market]:
        if self.scored_markets is None:
            return []
        return self.scored_markets.selected_markets
