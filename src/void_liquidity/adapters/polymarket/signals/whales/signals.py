from __future__ import annotations

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.candidates.repository import (
    list_latest_market_candidates,
)
from void_liquidity.adapters.polymarket.signals.whales.domain import (
    MarketSignal,
    MarketSignalResult,
    WhaleSignalProfile,
)


def list_market_signals(
    profile: WhaleSignalProfile,
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
    profile: WhaleSignalProfile,
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


class WhaleSignalService:
    def __init__(self, profile: WhaleSignalProfile) -> None:
        self.profile = profile

    def list(self, *, limit: int | None = None) -> MarketSignalResult:
        return list_market_signals(self.profile, limit=limit)
