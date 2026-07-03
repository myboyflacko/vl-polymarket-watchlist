from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, Field

from vl_polymarket_watchlist.polymarket.client import PolymarketDataClient


class ConditionPayload(BaseModel):
    condition_id: str
    event_id: str | None = None
    slug: str | None = None
    title: str | None = None
    question: str | None = None
    end_date: datetime | None = None
    active: bool = True
    closed: bool = False
    archived: bool = False
    enable_order_book: bool = True
    category: str | None = None
    tags: list[dict[str, Any]] = Field(default_factory=list)
    raw_latest_payload: dict[str, Any] = Field(default_factory=dict)


class TokenPayload(BaseModel):
    token_id: str
    condition_id: str
    outcome: str | None = None
    outcome_index: int | None = None
    opposite_token_id: str | None = None
    opposite_outcome: str | None = None
    active: bool = True
    closed: bool = False
    enable_order_book: bool = True


class MarketObservation(BaseModel):
    source: str
    observed_at: datetime
    condition: ConditionPayload
    token: TokenPayload
    event_slug: str | None = None
    event_title: str | None = None
    volume: Decimal | None = None
    liquidity: Decimal | None = None
    open_interest: Decimal | None = None
    last_trade_price: Decimal | None = None
    outcome_price: Decimal | None = None
    source_reason: str | None = None
    source_score: Decimal | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MarketCollectionError(BaseModel):
    source: str
    message: str


class CollectedMarkets(BaseModel):
    observations: list[MarketObservation] = Field(default_factory=list)
    errors: list[MarketCollectionError] = Field(default_factory=list)
    checked_count: int = 0
    generated_at: datetime

    @property
    def observed_count(self) -> int:
        return len(self.observations)


class DiscoveryRunResult(BaseModel):
    run_id: str
    source: str
    source_version: str
    status: str
    observations: list[MarketObservation] = Field(default_factory=list)
    errors: list[MarketCollectionError] = Field(default_factory=list)
    checked_count: int = 0
    observed_count: int = 0
    generated_at: datetime


class MarketDiscoverySource(Protocol):
    source: str
    source_version: str

    def config(self) -> dict[str, Any]:
        ...

    async def run(
        self,
        *,
        client: PolymarketDataClient,
        generated_at: datetime,
    ) -> CollectedMarkets:
        ...
