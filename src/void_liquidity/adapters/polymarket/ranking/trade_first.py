from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from void_liquidity.adapters.polymarket.discovery.whales_v2.domain import Whale, Whales


DEFAULT_TRADE_FIRST_RANKING_METHOD = "trade_first_percentile_v1"


@dataclass(frozen=True)
class TradeFirstRankingWeights:
    pnl: float = 0.30
    volume: float = 0.25
    trade_activity: float = 0.20
    recency: float = 0.15
    exposure: float = 0.10
    concentration_penalty: float = 0.10
    bottom_cut_percentile: float = 0.25


class RankedWhale(BaseModel):
    whale: Whale
    score: float


class WhaleRankingResult(BaseModel):
    method: str
    ranked_whales: list[RankedWhale]
    removed_wallets: list[str]

    @property
    def whales(self) -> list[Whale]:
        return [ranked.whale for ranked in self.ranked_whales]


def rank_trade_first_whales(
    whales: Whales,
    weights: TradeFirstRankingWeights | None = None,
) -> WhaleRankingResult:
    weights = weights or TradeFirstRankingWeights()

    if not whales.whales:
        return WhaleRankingResult(
            method=DEFAULT_TRADE_FIRST_RANKING_METHOD,
            ranked_whales=[],
            removed_wallets=[],
        )

    scores = _score_whales(whales.whales, weights)
    ranked = [
        RankedWhale(whale=whale, score=scores[whale.proxy_wallet])
        for whale in sorted(
            whales.whales,
            key=lambda item: scores[item.proxy_wallet],
            reverse=True,
        )
    ]
    keep_count = max(1, int(len(ranked) * (1 - weights.bottom_cut_percentile)))
    kept = ranked[:keep_count]
    removed = ranked[keep_count:]

    return WhaleRankingResult(
        method=DEFAULT_TRADE_FIRST_RANKING_METHOD,
        ranked_whales=kept,
        removed_wallets=[item.whale.proxy_wallet for item in removed],
    )


def _score_whales(
    whales: list[Whale],
    weights: TradeFirstRankingWeights,
) -> dict[str, float]:
    pnl = _percentile_scores(
        whales,
        lambda whale: whale.metrics.leaderboard.leaderboard_pnl_month,
    )
    volume = _percentile_scores(
        whales,
        lambda whale: whale.metrics.leaderboard.leaderboard_volume_month,
    )
    trade_activity = _percentile_scores(
        whales,
        lambda whale: whale.metrics.trades.trade_volume_30d,
    )
    recency = _percentile_scores(
        whales,
        lambda whale: whale.metrics.trades.last_trade_age_days,
        lower_is_better=True,
    )
    exposure = _percentile_scores(
        whales,
        lambda whale: whale.metrics.exposure.current_position_value,
    )
    market_concentration = _percentile_scores(
        whales,
        lambda whale: whale.metrics.markets.market_concentration_30d,
    )
    position_concentration = _percentile_scores(
        whales,
        lambda whale: whale.metrics.exposure.position_concentration,
    )

    return {
        whale.proxy_wallet: (
            weights.pnl * pnl[whale.proxy_wallet]
            + weights.volume * volume[whale.proxy_wallet]
            + weights.trade_activity * trade_activity[whale.proxy_wallet]
            + weights.recency * recency[whale.proxy_wallet]
            + weights.exposure * exposure[whale.proxy_wallet]
            - weights.concentration_penalty
            * max(
                market_concentration[whale.proxy_wallet],
                position_concentration[whale.proxy_wallet],
            )
        )
        for whale in whales
    }


def _percentile_scores(
    whales: list[Whale],
    value_getter,
    *,
    lower_is_better: bool = False,
) -> dict[str, float]:
    values = [
        (whale.proxy_wallet, value_getter(whale))
        for whale in whales
        if isinstance(value_getter(whale), int | float)
    ]

    if not values:
        return {whale.proxy_wallet: 0.0 for whale in whales}

    sorted_values = sorted(values, key=lambda item: item[1])
    percentile_by_wallet: dict[str, float] = {}

    for index, (wallet, _) in enumerate(sorted_values, start=1):
        percentile = index / len(sorted_values)
        percentile_by_wallet[wallet] = 1 - percentile if lower_is_better else percentile

    return {
        whale.proxy_wallet: percentile_by_wallet.get(whale.proxy_wallet, 0.0)
        for whale in whales
    }
