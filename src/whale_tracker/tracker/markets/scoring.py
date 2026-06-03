from __future__ import annotations

from collections.abc import Callable
from math import exp, sqrt

from pydantic import BaseModel, Field

from whale_tracker.tracker.markets.domain import (
    FilteredMarkets,
    Market,
    ScoredMarket,
    ScoredMarkets,
)


DEFAULT_MARKET_SCORING_PROFILE = "market_zscore_v1"


class ZScoreMarketScoringProfile(BaseModel):
    name: str = DEFAULT_MARKET_SCORING_PROFILE
    whale_count_weight: float = Field(default=1.0, ge=0)
    total_current_value_weight: float = Field(default=1.0, ge=0)
    value_per_wallet_weight: float = Field(default=1.0, ge=0)
    bottom_cut_percentile: float = Field(default=0.75, ge=0, le=1)
    score_scale: float = Field(default=1.0, gt=0)

    def run(
        self,
        filtered_markets: FilteredMarkets,
        *,
        limit: int | None = None,
    ) -> ScoredMarkets:
        if not filtered_markets.markets:
            return ScoredMarkets(
                markets=[],
                removed_markets=[],
                generated_at=filtered_markets.generated_at,
                profile_name=self.name,
            )

        scored_markets = self._scored_markets(filtered_markets.markets)
        ranked = [
            ScoredMarket(market=market, score=market.score)
            for market in sorted(
                scored_markets,
                key=lambda item: (
                    item.score,
                    item.whale_count,
                    item.total_current_value,
                ),
                reverse=True,
            )
        ]
        keep_count = max(1, int(len(ranked) * (1 - self.bottom_cut_percentile)))
        if limit is not None:
            keep_count = min(keep_count, limit)

        return ScoredMarkets(
            markets=ranked[:keep_count],
            removed_markets=ranked[keep_count:],
            generated_at=filtered_markets.generated_at,
            profile_name=self.name,
        )

    def _scored_markets(self, markets: list[Market]) -> list[Market]:
        whale_count = _z_scores(markets, lambda market: market.whale_count)
        total_current_value = _z_scores(
            markets,
            lambda market: market.total_current_value,
        )
        value_per_wallet = {
            market.token_id: _value_per_wallet(market)
            for market in markets
        }
        value_per_wallet_z_scores = _z_scores(
            markets,
            lambda market: value_per_wallet[market.token_id],
        )
        metric_weight_sum = (
            self.whale_count_weight
            + self.total_current_value_weight
            + self.value_per_wallet_weight
        )

        scored: list[Market] = []
        for market in markets:
            raw_score = (
                (
                    self.whale_count_weight * whale_count[market.token_id]
                    + self.total_current_value_weight
                    * total_current_value[market.token_id]
                    + self.value_per_wallet_weight
                    * value_per_wallet_z_scores[market.token_id]
                )
                / metric_weight_sum
                if metric_weight_sum
                else 0.0
            )
            score = _sigmoid_score(raw_score, scale=self.score_scale)
            scored.append(
                market.model_copy(
                    update={
                        "qualified": True,
                        "categories": [],
                        "category_scores": {},
                        "score": score,
                        "price_delta": market.cur_price - market.weighted_avg_price,
                        "price_delta_pct": _price_delta_pct(market),
                        "value_per_wallet": value_per_wallet[market.token_id],
                    }
                )
            )

        return scored


MarketScoringProfile = ZScoreMarketScoringProfile


def _z_scores(
    markets: list[Market],
    value_getter: Callable[[Market], float | int | None],
) -> dict[str, float]:
    values = [
        (market.token_id, float(value))
        for market in markets
        if isinstance((value := value_getter(market)), int | float)
    ]

    if not values:
        return {market.token_id: 0.0 for market in markets}

    mean = sum(value for _, value in values) / len(values)
    variance = sum((value - mean) ** 2 for _, value in values) / len(values)
    standard_deviation = sqrt(variance)

    if standard_deviation == 0:
        return {market.token_id: 0.0 for market in markets}

    z_score_by_token = {
        token_id: (value - mean) / standard_deviation
        for token_id, value in values
    }
    return {
        market.token_id: z_score_by_token.get(market.token_id, 0.0)
        for market in markets
    }


def _sigmoid_score(raw_score: float, *, scale: float) -> float:
    return 100 / (1 + exp(-raw_score * scale))


def _value_per_wallet(market: Market) -> float:
    return (
        market.total_current_value / market.whale_count
        if market.whale_count
        else 0.0
    )


def _price_delta_pct(market: Market) -> float | None:
    price_delta = market.cur_price - market.weighted_avg_price
    return price_delta / market.weighted_avg_price if market.weighted_avg_price else None
