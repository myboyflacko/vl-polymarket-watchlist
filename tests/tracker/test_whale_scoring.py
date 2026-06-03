from datetime import UTC, datetime

import pytest

from whale_tracker.tracker.whales.domain import (
    CollectionQuality,
    ExposureMetrics,
    FilteredWhales,
    LeaderboardMetrics,
    MarketMetrics,
    TradeMetrics,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
)
from whale_tracker.tracker.whales.scoring import (
    PercentileWhaleScoringProfile,
    ZScoreWhaleScoringProfile,
)


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_z_score_scoring_ranks_current_run_metrics() -> None:
    result = ZScoreWhaleScoringProfile(bottom_cut_percentile=0.5).run(
        _filtered_whales(
            [
                _whale(
                    "0x1",
                    pnl=100,
                    volume=100,
                    trade_volume=100,
                    last_trade_age_days=1,
                    exposure=100,
                ),
                _whale(
                    "0x2",
                    pnl=10,
                    volume=10,
                    trade_volume=10,
                    last_trade_age_days=5,
                    exposure=10,
                ),
            ]
        )
    )

    assert [entry.whale.proxy_wallet for entry in result.whales] == ["0x1"]
    assert [entry.whale.proxy_wallet for entry in result.removed_whales] == ["0x2"]


def test_z_score_scoring_uses_weighted_mean() -> None:
    result = ZScoreWhaleScoringProfile(
        pnl_weight=3,
        volume_weight=1,
        trade_activity_weight=0,
        recency_weight=0,
        exposure_weight=0,
        concentration_penalty_weight=0,
        bottom_cut_percentile=0,
    ).run(
        _filtered_whales(
            [
                _whale("0x1", pnl=20, volume=0),
                _whale("0x2", pnl=10, volume=10),
            ]
        )
    )

    scores = {entry.whale.proxy_wallet: entry.score for entry in result.whales}

    assert scores["0x1"] == pytest.approx(62.2459, rel=1e-4)
    assert scores["0x2"] == pytest.approx(37.7541, rel=1e-4)


def test_z_score_concentration_is_penalty_without_bonus() -> None:
    result = ZScoreWhaleScoringProfile(
        pnl_weight=0,
        volume_weight=0,
        trade_activity_weight=0,
        recency_weight=0,
        exposure_weight=0,
        concentration_penalty_weight=1,
        bottom_cut_percentile=0,
    ).run(
        _filtered_whales(
            [
                _whale("0x1", market_concentration=0.9),
                _whale("0x2", market_concentration=0.1),
            ]
        )
    )

    scores = {entry.whale.proxy_wallet: entry.score for entry in result.whales}

    assert scores["0x1"] == pytest.approx(26.8941, rel=1e-4)
    assert scores["0x2"] == pytest.approx(50.0)


def test_z_score_zero_variance_metrics_score_neutral() -> None:
    result = ZScoreWhaleScoringProfile(
        pnl_weight=1,
        volume_weight=0,
        trade_activity_weight=0,
        recency_weight=0,
        exposure_weight=0,
        concentration_penalty_weight=0,
        bottom_cut_percentile=0,
    ).run(
        _filtered_whales(
            [
                _whale("0x1", pnl=10),
                _whale("0x2", pnl=10),
            ]
        )
    )

    assert [entry.score for entry in result.whales] == [50.0, 50.0]


def test_percentile_scoring_profile_is_usable() -> None:
    result = PercentileWhaleScoringProfile(
        volume_weight=0,
        trade_activity_weight=0,
        recency_weight=0,
        exposure_weight=0,
        concentration_penalty_weight=0,
        bottom_cut_percentile=0.5,
    ).run(
        _filtered_whales(
            [
                _whale("0x1", pnl=100),
                _whale("0x2", pnl=10),
            ]
        )
    )

    assert [entry.whale.proxy_wallet for entry in result.whales] == ["0x1"]
    assert result.profile_name == "trade_first_percentile_v1"


def _filtered_whales(whales: list[Whale]) -> FilteredWhales:
    return FilteredWhales(
        whales=whales,
        checked_wallet_count=len(whales),
        generated_at=NOW,
        profile_name="test_filter",
    )


def _whale(
    proxy_wallet: str,
    *,
    pnl: float = 0,
    volume: float = 0,
    trade_volume: float = 0,
    last_trade_age_days: float | None = None,
    exposure: float = 0,
    market_concentration: float = 0,
    position_concentration: float = 0,
) -> Whale:
    return Whale(
        identity=WhaleIdentity(proxy_wallet=proxy_wallet),
        metrics=WhaleMetrics(
            leaderboard=LeaderboardMetrics(
                leaderboard_pnl_month=pnl,
                leaderboard_volume_month=volume,
                candidate_source="both",
            ),
            trades=TradeMetrics(
                trade_volume_30d=trade_volume,
                last_trade_age_days=last_trade_age_days,
            ),
            markets=MarketMetrics(
                market_concentration_30d=market_concentration,
            ),
            exposure=ExposureMetrics(
                current_position_value=exposure,
                position_concentration=position_concentration,
            ),
            collection_quality=CollectionQuality(),
        ),
    )
