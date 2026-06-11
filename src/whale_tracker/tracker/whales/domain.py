from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CandidateSource = Literal["pnl", "volume", "both"]


@dataclass(frozen=True)
class LeaderboardEntry:
    proxy_wallet: str
    row: dict[str, Any]


@dataclass(frozen=True)
class WhaleCandidate:
    proxy_wallet: str
    pnl_entry: dict[str, Any] | None
    volume_entry: dict[str, Any] | None
    candidate_collection_complete: bool


class WhaleIdentity(BaseModel):
    proxy_wallet: str
    name: str | None = None
    pseudonym: str | None = None
    profile_image: str | None = None


class LeaderboardObservationMetrics(BaseModel):
    candidate_source: CandidateSource
    pnl_rank: int | None = None
    volume_rank: int | None = None
    leaderboard_pnl: float = 0.0
    leaderboard_volume: float = 0.0


class LeaderboardObservation(BaseModel):
    proxy_wallet: str
    metrics: LeaderboardObservationMetrics
    generated_at: datetime


class Whale(BaseModel):
    identity: WhaleIdentity
    observation: LeaderboardObservation

    @property
    def proxy_wallet(self) -> str:
        return self.identity.proxy_wallet


class Whales(BaseModel):
    whales: list[Whale] = Field(default_factory=list)
    candidate_wallet_count: int
    checked_wallet_count: int
    generated_at: datetime
    profile_version: str

    @property
    def wallet_count(self) -> int:
        return len(self.whales)

    def proxy_wallets(self) -> list[str]:
        return [whale.proxy_wallet for whale in self.whales]


class WhaleRunResult(BaseModel):
    run_id: str
    whales: Whales

    @property
    def observed_whales(self) -> list[Whale]:
        return self.whales.whales


class WhaleTrackingResult(WhaleRunResult):
    @property
    def discovery_run_id(self) -> str:
        return self.run_id
