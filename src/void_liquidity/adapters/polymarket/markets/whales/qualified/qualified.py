from __future__ import annotations

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.candidates.repository import (
    list_latest_market_candidates,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    QualifiedMarket,
    QualifiedMarketResult,
    WhaleQualifiedMarketProfile,
)


def list_qualified_markets(
    profile: WhaleQualifiedMarketProfile,
    *,
    limit: int | None = None,
) -> QualifiedMarketResult:
    candidates = list_latest_market_candidates()
    qualified_markets = [
        qualified_market
        for candidate in candidates
        if (
            qualified_market := _qualified_market(
                candidate=candidate,
                profile=profile,
            )
        )
        is not None
    ]
    sorted_markets = sorted(
        qualified_markets,
        key=lambda qualified_market: qualified_market.score,
        reverse=True,
    )
    if limit is not None:
        sorted_markets = sorted_markets[:limit]

    return QualifiedMarketResult(profile=profile, qualified_markets=sorted_markets)


def _qualified_market(
    *,
    candidate: MarketCandidate,
    profile: WhaleQualifiedMarketProfile,
) -> QualifiedMarket | None:
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

    return QualifiedMarket(
        profile=profile.name,
        candidate=candidate,
        score=score,
        price_delta=price_delta,
        price_delta_pct=price_delta_pct,
        value_per_wallet=value_per_wallet,
    )


class WhaleQualifiedMarketService:
    def __init__(self, profile: WhaleQualifiedMarketProfile) -> None:
        self.profile = profile

    def list(self, *, limit: int | None = None) -> QualifiedMarketResult:
        return list_qualified_markets(self.profile, limit=limit)
