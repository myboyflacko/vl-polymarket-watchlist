from __future__ import annotations

from collections.abc import Iterable, Sequence

from whale_tracker.tracker.markets.domain import (
    FilteredMarkets,
    Market,
    ScoredMarket,
    ScoredMarkets,
)
from whale_tracker.tracker.markets.profiles import MarketScoringProfile


def score_markets(
    *,
    filtered_markets: FilteredMarkets,
    profiles: Sequence[MarketScoringProfile],
    limit: int | None = None,
) -> ScoredMarkets:
    scored = [
        ScoredMarket(market=market, score=market.score)
        for market in _rank_scored_markets(
            qualify_markets(filtered_markets.markets, profiles=profiles),
            limit=limit,
        )
    ]

    scored_tokens = {entry.market.token_id for entry in scored}
    removed = [
        ScoredMarket(market=market, score=market.score)
        for market in qualify_markets(filtered_markets.markets, profiles=profiles)
        if market.token_id not in scored_tokens
    ]

    return ScoredMarkets(
        markets=scored,
        removed_markets=removed,
        generated_at=filtered_markets.generated_at,
        profile_name="qualified_market_profiles",
    )


def qualify_markets(
    markets: Iterable[Market],
    *,
    profiles: Sequence[MarketScoringProfile],
) -> list[Market]:
    return [
        qualify_market(market=market, profiles=profiles)
        for market in markets
    ]


def qualify_market(
    *,
    market: Market,
    profiles: Sequence[MarketScoringProfile],
) -> Market:
    category_scores: dict = {}
    price_delta = market.cur_price - market.weighted_avg_price
    value_per_wallet = (
        market.total_current_value / market.whale_count
        if market.whale_count
        else 0.0
    )
    price_delta_pct = (
        price_delta / market.weighted_avg_price
        if market.weighted_avg_price
        else None
    )

    for profile in profiles:
        score = _score_for_profile(
            market=market,
            profile=profile,
            price_delta=price_delta,
            value_per_wallet=value_per_wallet,
        )
        if score is not None:
            category_scores[profile.name] = score

    return market.model_copy(
        update={
            "qualified": bool(category_scores),
            "categories": list(category_scores),
            "category_scores": category_scores,
            "score": max(category_scores.values(), default=0.0),
            "price_delta": price_delta,
            "price_delta_pct": price_delta_pct,
            "value_per_wallet": value_per_wallet,
        }
    )


def _rank_scored_markets(
    markets: list[Market],
    *,
    limit: int | None,
) -> list[Market]:
    qualified_markets = [market for market in markets if market.qualified]
    qualified_markets.sort(
        key=lambda market: (
            market.score,
            market.whale_count,
            market.total_current_value,
        ),
        reverse=True,
    )
    if limit is not None:
        return qualified_markets[:limit]

    return qualified_markets


def _score_for_profile(
    *,
    market: Market,
    profile: MarketScoringProfile,
    price_delta: float,
    value_per_wallet: float,
) -> float | None:
    if market.total_current_value < profile.min_total_current_value:
        return None

    if value_per_wallet < profile.min_value_per_wallet:
        return None

    match profile.name:
        case "confirmed":
            if price_delta <= 0:
                return None
            return price_delta * value_per_wallet
        case "pain":
            if price_delta >= 0:
                return None
            return abs(price_delta) * value_per_wallet
        case "high_value":
            return market.total_current_value
        case "value_per_wallet":
            return value_per_wallet
