from __future__ import annotations

from collections.abc import Callable
from math import sqrt

from pydantic import BaseModel, Field

from whale_tracker.tracker.whales.domain import (
    FilteredWhales,
    ScoredWhale,
    ScoredWhales,
    Whale,
)


DEFAULT_Z_SCORE_WHALE_SCORING_PROFILE = "trade_first_zscore_v1"
PERCENTILE_WHALE_SCORING_PROFILE = "trade_first_percentile_v1"


class BaseWhaleScoringProfile(BaseModel):
    name: str
    pnl_weight: float = Field(default=0.30, ge=0)
    volume_weight: float = Field(default=0.25, ge=0)
    trade_activity_weight: float = Field(default=0.20, ge=0)
    recency_weight: float = Field(default=0.15, ge=0)
    exposure_weight: float = Field(default=0.10, ge=0)
    concentration_penalty_weight: float = Field(default=0.10, ge=0)
    bottom_cut_percentile: float = Field(default=0.75, ge=0, le=1)

    def run(self, filtered_whales: FilteredWhales) -> ScoredWhales:
        if not filtered_whales.whales:
            return ScoredWhales(
                whales=[],
                removed_whales=[],
                generated_at=filtered_whales.generated_at,
                profile_name=self.name,
            )

        scores = self._scores(filtered_whales.whales)
        ranked = [
            ScoredWhale(whale=whale, score=scores[whale.proxy_wallet])
            for whale in sorted(
                filtered_whales.whales,
                key=lambda item: scores[item.proxy_wallet],
                reverse=True,
            )
        ]
        keep_count = max(1, int(len(ranked) * (1 - self.bottom_cut_percentile)))

        return ScoredWhales(
            whales=ranked[:keep_count],
            removed_whales=ranked[keep_count:],
            generated_at=filtered_whales.generated_at,
            profile_name=self.name,
        )

    def _scores(self, whales: list[Whale]) -> dict[str, float]:
        raise NotImplementedError


class PercentileWhaleScoringProfile(BaseWhaleScoringProfile):
    name: str = PERCENTILE_WHALE_SCORING_PROFILE

    def _scores(self, whales: list[Whale]) -> dict[str, float]:
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
                self.pnl_weight * pnl[whale.proxy_wallet]
                + self.volume_weight * volume[whale.proxy_wallet]
                + self.trade_activity_weight * trade_activity[whale.proxy_wallet]
                + self.recency_weight * recency[whale.proxy_wallet]
                + self.exposure_weight * exposure[whale.proxy_wallet]
                - self.concentration_penalty_weight
                * max(
                    market_concentration[whale.proxy_wallet],
                    position_concentration[whale.proxy_wallet],
                )
            )
            for whale in whales
        }


class ZScoreWhaleScoringProfile(BaseWhaleScoringProfile):
    name: str = DEFAULT_Z_SCORE_WHALE_SCORING_PROFILE

    def _scores(self, whales: list[Whale]) -> dict[str, float]:
        pnl = _z_scores(
            whales,
            lambda whale: whale.metrics.leaderboard.leaderboard_pnl_month,
        )
        volume = _z_scores(
            whales,
            lambda whale: whale.metrics.leaderboard.leaderboard_volume_month,
        )
        trade_activity = _z_scores(
            whales,
            lambda whale: whale.metrics.trades.trade_volume_30d,
        )
        recency = _z_scores(
            whales,
            lambda whale: whale.metrics.trades.last_trade_age_days,
            lower_is_better=True,
        )
        exposure = _z_scores(
            whales,
            lambda whale: whale.metrics.exposure.current_position_value,
        )
        market_concentration = _z_scores(
            whales,
            lambda whale: whale.metrics.markets.market_concentration_30d,
        )
        position_concentration = _z_scores(
            whales,
            lambda whale: whale.metrics.exposure.position_concentration,
        )
        metric_weight_sum = (
            self.pnl_weight
            + self.volume_weight
            + self.trade_activity_weight
            + self.recency_weight
            + self.exposure_weight
        )

        return {
            whale.proxy_wallet: (
                (
                    self.pnl_weight * pnl[whale.proxy_wallet]
                    + self.volume_weight * volume[whale.proxy_wallet]
                    + self.trade_activity_weight * trade_activity[whale.proxy_wallet]
                    + self.recency_weight * recency[whale.proxy_wallet]
                    + self.exposure_weight * exposure[whale.proxy_wallet]
                )
                / metric_weight_sum
                if metric_weight_sum
                else 0.0
            )
            - self.concentration_penalty_weight
            * max(
                0.0,
                market_concentration[whale.proxy_wallet],
                position_concentration[whale.proxy_wallet],
            )
            for whale in whales
        }


WhaleScoringProfile = ZScoreWhaleScoringProfile | PercentileWhaleScoringProfile


def _z_scores(
    whales: list[Whale],
    value_getter: Callable[[Whale], float | int | None],
    *,
    lower_is_better: bool = False,
) -> dict[str, float]:
    values = [
        (whale.proxy_wallet, float(value))
        for whale in whales
        if isinstance((value := value_getter(whale)), int | float)
    ]

    if not values:
        return {whale.proxy_wallet: 0.0 for whale in whales}

    mean = sum(value for _, value in values) / len(values)
    variance = sum((value - mean) ** 2 for _, value in values) / len(values)
    standard_deviation = sqrt(variance)

    if standard_deviation == 0:
        return {whale.proxy_wallet: 0.0 for whale in whales}

    z_score_by_wallet = {
        wallet: (value - mean) / standard_deviation for wallet, value in values
    }
    if lower_is_better:
        z_score_by_wallet = {
            wallet: -score for wallet, score in z_score_by_wallet.items()
        }

    return {
        whale.proxy_wallet: z_score_by_wallet.get(whale.proxy_wallet, 0.0)
        for whale in whales
    }


def _percentile_scores(
    whales: list[Whale],
    value_getter: Callable[[Whale], float | int | None],
    *,
    lower_is_better: bool = False,
) -> dict[str, float]:
    values = [
        (whale.proxy_wallet, value)
        for whale in whales
        if isinstance((value := value_getter(whale)), int | float)
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
