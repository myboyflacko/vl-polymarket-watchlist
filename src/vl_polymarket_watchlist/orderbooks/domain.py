from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


PARSER_VERSION = "orderbook_parser_v1"


class OrderBookLevel(BaseModel):
    price: Decimal
    size: Decimal


class OrderBookCollectionItemPayload(BaseModel):
    condition_id: str
    token_id: str
    slug: str | None = None
    title: str | None = None
    outcome: str | None = None
    priority: str | None = None
    sources: list[str] = Field(default_factory=list)
    watchlist_reason: str | None = None
    days_to_expiry: Decimal | None = None
    collect_orderbook: bool = True
    selected_at: datetime


class ParsedOrderBook(BaseModel):
    condition_id: str
    token_id: str
    generated_at: datetime
    exchange_timestamp: datetime | None = None
    exchange_timestamp_raw: str | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    midpoint: Decimal | None = None
    spread: Decimal | None = None
    last_trade_price: Decimal | None = None
    bid_depth_top_1: Decimal | None = None
    ask_depth_top_1: Decimal | None = None
    bid_depth_top_3: Decimal | None = None
    ask_depth_top_3: Decimal | None = None
    bid_depth_top_5: Decimal | None = None
    ask_depth_top_5: Decimal | None = None
    bid_levels_count: int = 0
    ask_levels_count: int = 0
    min_order_size: Decimal | None = None
    tick_size: Decimal | None = None
    negative_risk: bool | None = None
    bids: list[dict[str, Any]] = Field(default_factory=list)
    asks: list[dict[str, Any]] = Field(default_factory=list)
    book_hash: str | None = None
    valid_orderbook: bool = False
    invalid_reason: str | None = None
    parser_version: str = PARSER_VERSION
    api_status: int | None = None
    api_error: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OrderBookCollectionResult(BaseModel):
    run_id: str
    selected_token_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    snapshots: list[ParsedOrderBook] = Field(default_factory=list)
    generated_at: datetime
