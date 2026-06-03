from datetime import UTC, datetime

from whale_tracker.tracker.whales.domain import (
    CollectionQuality,
    ExposureMetrics,
    LeaderboardMetrics,
    MarketMetrics,
    TradeMetrics,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    Whales,
)
from whale_tracker.tracker.whales.filter import DefaultWhaleFilterProfile


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_default_whale_filter_profile_filters_by_trade_count_and_exposure() -> None:
    result = DefaultWhaleFilterProfile(
        min_trade_count_30d=2,
        min_current_position_value=100,
    ).run(
        Whales(
            whales=[
                _whale("0x1", trade_count=2, exposure=100),
                _whale("0x2", trade_count=1, exposure=100),
                _whale("0x3", trade_count=2, exposure=50),
            ],
            candidate_wallet_count=3,
            checked_wallet_count=3,
            generated_at=NOW,
            profile_version="test_discovery",
        )
    )

    assert [whale.proxy_wallet for whale in result.whales] == ["0x1"]
    assert [whale.proxy_wallet for whale in result.removed_whales] == ["0x2", "0x3"]
    assert result.checked_wallet_count == 3
    assert result.generated_at == NOW
    assert result.profile_name == "default_whale_filter"


def _whale(proxy_wallet: str, *, trade_count: int, exposure: float) -> Whale:
    return Whale(
        identity=WhaleIdentity(proxy_wallet=proxy_wallet),
        metrics=WhaleMetrics(
            leaderboard=LeaderboardMetrics(candidate_source="both"),
            trades=TradeMetrics(trade_count_30d=trade_count),
            markets=MarketMetrics(),
            exposure=ExposureMetrics(current_position_value=exposure),
            collection_quality=CollectionQuality(),
        ),
    )
