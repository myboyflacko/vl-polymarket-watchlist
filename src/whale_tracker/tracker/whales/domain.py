from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


CandidateSource = Literal["pnl", "volume", "both"]
TradeSortOrder = Literal["desc", "unknown"]
WalletCollectionStage = Literal["trades", "current_positions"]


class WhaleIdentity(BaseModel):
    proxy_wallet: str
    name: str | None = None
    pseudonym: str | None = None
    profile_image: str | None = None


class LeaderboardMetrics(BaseModel):
    leaderboard_pnl_month: float = 0.0
    leaderboard_volume_month: float = 0.0
    pnl_rank: int | None = None
    volume_rank: int | None = None
    candidate_source: CandidateSource


class TradeMetrics(BaseModel):
    trade_count_30d: int = 0
    trade_count_7d: int = 0
    trade_volume_30d: float = 0.0
    trade_volume_7d: float = 0.0
    last_trade_at: datetime | None = None
    last_trade_age_days: float | None = None
    avg_trade_size_30d: float = 0.0
    buy_volume_30d: float = 0.0
    sell_volume_30d: float = 0.0
    net_flow_30d: float = 0.0
    net_flow_ratio_30d: float | None = None
    buy_sell_ratio_30d: float | None = None


class MarketMetrics(BaseModel):
    unique_markets_30d: int = 0
    market_concentration_30d: float = 0.0
    largest_market_volume_30d: float = 0.0


class ExposureMetrics(BaseModel):
    current_position_value: float = 0.0
    open_position_count: int = 0
    largest_position_value: float = 0.0
    position_concentration: float = 0.0


class CollectionQuality(BaseModel):
    trades_complete: bool = True
    trades_sort_order: TradeSortOrder = "desc"
    invalid_trade_row_count: int = 0
    current_positions_complete: bool = True
    candidate_collection_complete: bool = True


class WhaleMetrics(BaseModel):
    leaderboard: LeaderboardMetrics
    trades: TradeMetrics
    markets: MarketMetrics
    exposure: ExposureMetrics
    collection_quality: CollectionQuality


class Whale(BaseModel):
    identity: WhaleIdentity
    condition_ids_30d: list[str] = Field(default_factory=list)
    metrics: WhaleMetrics

    @property
    def proxy_wallet(self) -> str:
        return self.identity.proxy_wallet


class WalletCollectionError(BaseModel):
    proxy_wallet: str
    stage: WalletCollectionStage
    error_type: str
    error: str


class Whales(BaseModel):
    whales: list[Whale]
    candidate_wallet_count: int
    checked_wallet_count: int
    generated_at: datetime
    profile_version: str
    collection_errors: list[WalletCollectionError] = Field(default_factory=list)

    @property
    def wallet_count(self) -> int:
        return len(self.whales)

    @property
    def successful_wallet_count(self) -> int:
        return len(self.whales)

    @property
    def failed_wallet_count(self) -> int:
        return len(self.collection_errors)

    @property
    def partial(self) -> bool:
        return bool(self.collection_errors)

    def proxy_wallets(self) -> list[str]:
        return [whale.proxy_wallet for whale in self.whales]


class FilteredWhales(BaseModel):
    whales: list[Whale]
    removed_whales: list[Whale] = Field(default_factory=list)
    checked_wallet_count: int
    generated_at: datetime
    profile_name: str

    @property
    def wallet_count(self) -> int:
        return len(self.whales)

    @property
    def removed_wallet_count(self) -> int:
        return len(self.removed_whales)

    def proxy_wallets(self) -> list[str]:
        return [whale.proxy_wallet for whale in self.whales]


class ScoredWhale(BaseModel):
    whale: Whale
    score: float


class ScoredWhales(BaseModel):
    whales: list[ScoredWhale]
    removed_whales: list[ScoredWhale] = Field(default_factory=list)
    generated_at: datetime
    profile_name: str

    @property
    def wallet_count(self) -> int:
        return len(self.whales)

    @property
    def removed_wallet_count(self) -> int:
        return len(self.removed_whales)

    @property
    def selected_whales(self) -> list[Whale]:
        return [scored.whale for scored in self.whales]

    @property
    def removed_wallets(self) -> list[str]:
        return [scored.whale.proxy_wallet for scored in self.removed_whales]


RankedWhale = ScoredWhale


class WhaleSelectionRankingResult(BaseModel):
    method: str
    ranked_whales: list[ScoredWhale]
    removed_whales: list[ScoredWhale]

    @property
    def whales(self) -> list[Whale]:
        return [ranked.whale for ranked in self.ranked_whales]

    @property
    def removed_wallets(self) -> list[str]:
        return [ranked.whale.proxy_wallet for ranked in self.removed_whales]


class WhaleRunResult(BaseModel):
    run_id: str
    whales: Whales
    filtered_whales: FilteredWhales
    scored_whales: ScoredWhales | None = None
    collection_errors: list[WalletCollectionError] = Field(default_factory=list)

    @property
    def result_whales(self) -> FilteredWhales | ScoredWhales:
        return self.scored_whales or self.filtered_whales


class WhaleTrackingResult(WhaleRunResult):
    @property
    def discovery_run_id(self) -> str:
        return self.run_id

    @property
    def selection_run_id(self) -> str:
        return self.run_id

    @property
    def prefiltered_whales(self) -> Whales:
        return self.whales

    @property
    def selected_whales(self) -> list[Whale]:
        if self.scored_whales is not None:
            return self.scored_whales.selected_whales
        return self.filtered_whales.whales

    @property
    def removed_whales(self) -> list[ScoredWhale]:
        if self.scored_whales is not None:
            return self.scored_whales.removed_whales
        return [ScoredWhale(whale=whale, score=0.0) for whale in self.filtered_whales.removed_whales]
