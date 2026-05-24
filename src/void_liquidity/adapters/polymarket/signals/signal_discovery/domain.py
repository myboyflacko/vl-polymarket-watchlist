from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Candidate:
    proxy_wallet: str
    source: str
    matched_pools: list[str]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "Candidate":
        return cls(
            proxy_wallet=payload["proxy_wallet"],
            source=payload["source"],
            matched_pools=list(payload["matched_pools"]),
        )

    def as_metrics_payload(self) -> dict[str, Any]:
        return {
            "proxy_wallet": self.proxy_wallet,
            "source": self.source,
            "matched_pools": self.matched_pools,
        }


@dataclass(frozen=True)
class CandidateEntries:
    pnl_entries: dict[str, dict[str, Any]]
    vol_entries: dict[str, dict[str, Any]]
    candidates: list[Candidate]
    pool_summary: Counter[str]


@dataclass(frozen=True)
class CandidateValidation:
    candidate: Candidate
    whale: dict[str, Any] | None
    reject_reasons: list[str]

    @property
    def accepted(self) -> bool:
        return self.whale is not None


@dataclass(frozen=True)
class CandidateScan:
    whales: dict[str, dict[str, Any]]
    reject_summary: Counter[str]
    reject_group_summary: dict[str, Counter[str]]
    checked_wallet_count: int
    checked_group_summary: Counter[str]


@dataclass(frozen=True)
class PagedRows:
    rows: list[dict[str, Any]]
    complete: bool
    unknown_timestamp_count: int = 0
    truncated: bool = False

    def __iter__(self):
        yield self.rows
        yield self.complete


@dataclass(frozen=True)
class PersistContext:
    reject_summary: Counter[str]
    reject_group_summary: dict[str, Counter[str]]
    checked_wallet_count: int
    checked_group_summary: Counter[str]
    candidate_wallet_count: int
    candidate_pool_summary: Counter[str] = field(default_factory=Counter)
    path: str | Path | None = None
    generated_at: datetime | None = None
    run_id: str | None = None
    started_at: datetime | None = None
