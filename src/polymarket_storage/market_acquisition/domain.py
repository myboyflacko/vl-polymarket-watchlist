from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from polymarket_storage.polymarket.client import PolymarketDataClient


class Market(BaseModel):
    token_id: str
    condition_id: str
    title: str = ""
    slug: str = ""
    outcome: str = ""
    opposite_token_id: str | None = None
    opposite_outcome: str | None = None
    end_date: date | None = None


class MarketCollectionError(BaseModel):
    source: str
    message: str


class CollectedMarkets(BaseModel):
    markets: list[Market] = Field(default_factory=list)
    errors: list[MarketCollectionError] = Field(default_factory=list)
    checked_market_count: int = 0
    generated_at: datetime

    @property
    def market_count(self) -> int:
        return len(self.markets)


class CollectorRunResult(BaseModel):
    run_id: str
    strategy_name: str
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    markets: list[Market] = Field(default_factory=list)
    errors: list[MarketCollectionError] = Field(default_factory=list)
    checked_market_count: int = 0
    stored_market_count: int = 0
    generated_at: datetime


class MarketCollectorStrategy(Protocol):
    name: str

    def params(self) -> dict[str, Any]:
        ...

    async def run(
        self,
        *,
        client: PolymarketDataClient,
        generated_at: datetime,
    ) -> CollectedMarkets:
        ...
