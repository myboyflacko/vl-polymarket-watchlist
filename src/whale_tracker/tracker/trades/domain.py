from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TradeSource(BaseModel):
    proxy_wallet: str
    condition_id: str
    market_ids_by_token: dict[str, int] = Field(default_factory=dict)


class Trade(BaseModel):
    proxy_wallet: str
    condition_id: str
    trade_key: str
    market_id: int | None = None
    token_id: str | None = None
    side: str | None = None
    outcome: str | None = None
    price: float | None = None
    size: float | None = None
    value: float | None = None
    trade_timestamp: datetime | None = None
    transaction_hash: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


class TrackedTrade(Trade):
    run_id: str
    market_run_id: str


class TrackedTrades(BaseModel):
    trades: list[TrackedTrade] = Field(default_factory=list)
    run_id: str
    market_run_id: str
    generated_at: datetime

    @property
    def trade_count(self) -> int:
        return len(self.trades)


class TradeCollectionError(BaseModel):
    proxy_wallet: str
    condition_id: str
    message: str


class Trades(BaseModel):
    trades: list[Trade] = Field(default_factory=list)
    errors: list[TradeCollectionError] = Field(default_factory=list)
    checked_source_count: int = 0
    generated_at: datetime


class TradeRunResult(BaseModel):
    run_id: str
    market_run_id: str
    collected_trades: Trades
    tracked_trades: TrackedTrades

    @property
    def errors(self) -> list[TradeCollectionError]:
        return self.collected_trades.errors


class TradeTrackingResult(TradeRunResult):
    @property
    def trades(self) -> list[TrackedTrade]:
        return self.tracked_trades.trades
