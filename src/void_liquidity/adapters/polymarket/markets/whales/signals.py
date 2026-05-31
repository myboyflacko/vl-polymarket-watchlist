from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from void_liquidity.adapters.polymarket.markets.whales.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.repository import (
    list_latest_market_candidates,
)


MarketSignalProfileName = Literal[
    "confirmed",
    "pain",
    "high_value",
    "value_per_wallet",
]


class MarketSignalProfile(BaseModel):
    name: MarketSignalProfileName
    min_total_current_value: float = Field(default=0.0, ge=0)
    min_value_per_wallet: float = Field(default=0.0, ge=0)


class MarketSignal(BaseModel):
    profile: MarketSignalProfileName
    candidate: MarketCandidate
    score: float
    price_delta: float
    price_delta_pct: float | None
    value_per_wallet: float


class MarketSignalResult(BaseModel):
    profile: MarketSignalProfile
    signals: list[MarketSignal]


def list_market_signals(
    profile: MarketSignalProfile,
    *,
    limit: int | None = None,
) -> MarketSignalResult:
    candidates = list_latest_market_candidates()
    signals = [
        signal
        for candidate in candidates
        if (signal := _market_signal(candidate=candidate, profile=profile)) is not None
    ]
    sorted_signals = sorted(signals, key=lambda signal: signal.score, reverse=True)
    if limit is not None:
        sorted_signals = sorted_signals[:limit]

    return MarketSignalResult(profile=profile, signals=sorted_signals)


def _market_signal(
    *,
    candidate: MarketCandidate,
    profile: MarketSignalProfile,
) -> MarketSignal | None:
    price_delta = candidate.cur_price - candidate.weighted_avg_price
    value_per_wallet = (
        candidate.total_current_value / candidate.whale_count
        if candidate.whale_count
        else 0.0
    )
    price_delta_pct = (
        price_delta / candidate.weighted_avg_price
        if candidate.weighted_avg_price
        else None
    )

    if candidate.total_current_value < profile.min_total_current_value:
        return None

    if value_per_wallet < profile.min_value_per_wallet:
        return None

    match profile.name:
        case "confirmed":
            if price_delta <= 0:
                return None
            score = price_delta * value_per_wallet
        case "pain":
            if price_delta >= 0:
                return None
            score = abs(price_delta) * value_per_wallet
        case "high_value":
            score = candidate.total_current_value
        case "value_per_wallet":
            score = value_per_wallet

    return MarketSignal(
        profile=profile.name,
        candidate=candidate,
        score=score,
        price_delta=price_delta,
        price_delta_pct=price_delta_pct,
        value_per_wallet=value_per_wallet,
    )
