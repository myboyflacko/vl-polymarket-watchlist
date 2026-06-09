from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrderBookLevel(BaseModel):
    price: float
    size: float


class TrackedMarketOrderBookSource(BaseModel):
    tracked_market_id: int
    token_id: str
    condition_id: str
    title: str
    slug: str
    outcome: str


class OrderBookSnapshot(BaseModel):
    tracked_market_id: int
    token_id: str
    condition_id: str
    market: str
    exchange_timestamp: datetime | None = None
    exchange_timestamp_raw: str | None = None
    book_hash: str
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    midpoint: float | None = None
    min_order_size: float | None = None
    tick_size: float | None = None
    negative_risk: bool = False
    last_trade_price: float | None = None
    generated_at: datetime


class TrackedOrderBook(OrderBookSnapshot):
    run_id: str
    market_run_id: str


class TrackedOrderBooks(BaseModel):
    orderbooks: list[TrackedOrderBook] = Field(default_factory=list)
    run_id: str
    market_run_id: str
    generated_at: datetime
    depth: int

    @property
    def orderbook_count(self) -> int:
        return len(self.orderbooks)


class OrderBookCollectionError(BaseModel):
    token_id: str
    message: str


class OrderBooks(BaseModel):
    snapshots: list[OrderBookSnapshot] = Field(default_factory=list)
    errors: list[OrderBookCollectionError] = Field(default_factory=list)
    checked_market_count: int = 0
    generated_at: datetime
    depth: int


class OrderBookRunResult(BaseModel):
    run_id: str
    market_run_id: str
    collected_orderbooks: OrderBooks
    tracked_orderbooks: TrackedOrderBooks

    @property
    def errors(self) -> list[OrderBookCollectionError]:
        return self.collected_orderbooks.errors


class OrderBookTrackingResult(OrderBookRunResult):
    @property
    def orderbooks(self) -> list[TrackedOrderBook]:
        return self.tracked_orderbooks.orderbooks
