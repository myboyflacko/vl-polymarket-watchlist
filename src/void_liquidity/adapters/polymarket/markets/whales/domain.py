from __future__ import annotations

from datetime import date

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


class MarketCandidate(BaseModel):
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


class WhalePositionCollectionError(BaseModel):
    proxy_wallet: str
    message: str


class WhaleMarketCandidates(BaseModel):
    candidates: list[MarketCandidate] = Field(default_factory=list)
    positions: list[WhalePosition] = Field(default_factory=list)
    errors: list[WhalePositionCollectionError] = Field(default_factory=list)
