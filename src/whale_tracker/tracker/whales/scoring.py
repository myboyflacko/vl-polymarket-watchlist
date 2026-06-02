from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from whale_tracker.tracker.whales.domain import (
    FilteredWhales,
    ScoredWhale,
    ScoredWhales,
    Whale,
)


DEFAULT_WHALE_SCORING_PROFILE = "trade_first_percentile_v1"


class WhaleScoringProfile(BaseModel):
    name: str = DEFAULT_WHALE_SCORING_PROFILE
    pnl_weight: float = Field(default=0.30, ge=0)
    volume_weight: float = Field(default=0.25, ge=0)
    trade_activity_weight: float = Field(default=0.20, ge=0)
    recency_weight: float = Field(default=0.15, ge=0)
    exposure_weight: float = Field(default=0.10, ge=0)
    concentration_penalty_weight: float = Field(default=0.10, ge=0)
    bottom_cut_percentile: float = Field(default=0.25, ge=0, le=1)


def score_whales(
    *,
    filtered_whales: FilteredWhales,
    profile: WhaleScoringProfile,
) -> ScoredWhales:
    if not filtered_whales.whales:
        return ScoredWhales(
            whales=[],
            removed_whales=[],
            generated_at=filtered_whales.generated_at,
            profile_name=profile.name,
        )

    scores = _score_whales(whales=filtered_whales.whales, profile=profile)
    ranked = [
        ScoredWhale(whale=whale, score=scores[whale.proxy_wallet])
        for whale in sorted(
            filtered_whales.whales,
            key=lambda item: scores[item.proxy_wallet],
            reverse=True,
        )
    ]
    keep_count = max(1, int(len(ranked) * (1 - profile.bottom_cut_percentile)))

    return ScoredWhales(
        whales=ranked[:keep_count],
        removed_whales=ranked[keep_count:],
        generated_at=filtered_whales.generated_at,
        profile_name=profile.name,
    )


def _score_whales(
    *,
    whales: list[Whale],
    profile: WhaleScoringProfile,
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
            profile.pnl_weight * pnl[whale.proxy_wallet]
            + profile.volume_weight * volume[whale.proxy_wallet]
            + profile.trade_activity_weight * trade_activity[whale.proxy_wallet]
            + profile.recency_weight * recency[whale.proxy_wallet]
            + profile.exposure_weight * exposure[whale.proxy_wallet]
            - profile.concentration_penalty_weight
            * max(
                market_concentration[whale.proxy_wallet],
                position_concentration[whale.proxy_wallet],
            )
        )
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
