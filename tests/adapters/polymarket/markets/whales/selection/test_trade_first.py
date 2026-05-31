from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales.discovery.domain import (
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
from void_liquidity.adapters.polymarket.markets.whales.selection.ranking import (
    TradeFirstRankingWeights,
    rank_trade_first_whales,
)


NOW = datetime(2026, 5, 26, tzinfo=UTC)


def _whale(
    proxy_wallet: str,
    *,
    pnl: float,
    volume: float,
    trade_volume: float,
    last_trade_age_days: float,
    exposure: float,
    concentration: float = 0.1,
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
            markets=MarketMetrics(market_concentration_30d=concentration),
            exposure=ExposureMetrics(
                current_position_value=exposure,
                position_concentration=concentration,
            ),
            collection_quality=CollectionQuality(),
        ),
    )


def test_rank_trade_first_whales_sorts_by_composite_score_and_cuts_bottom_25() -> None:
    whales = Whales(
        whales=[
            _whale("wallet-1", pnl=10, volume=10, trade_volume=10, exposure=10, last_trade_age_days=5),
            _whale("wallet-2", pnl=20, volume=20, trade_volume=20, exposure=20, last_trade_age_days=4),
            _whale("wallet-3", pnl=30, volume=30, trade_volume=30, exposure=30, last_trade_age_days=3),
            _whale("wallet-4", pnl=40, volume=40, trade_volume=40, exposure=40, last_trade_age_days=1),
        ],
        candidate_wallet_count=4,
        checked_wallet_count=4,
        generated_at=NOW,
        profile_version="test",
    )

    result = rank_trade_first_whales(whales)

    assert [ranked.whale.proxy_wallet for ranked in result.ranked_whales] == [
        "wallet-4",
        "wallet-3",
        "wallet-2",
    ]
    assert result.removed_wallets == ["wallet-1"]
    assert result.removed_whales[0].score > 0


def test_rank_trade_first_whales_penalizes_extreme_concentration() -> None:
    whales = Whales(
        whales=[
            _whale(
                "focused",
                pnl=100,
                volume=100,
                trade_volume=100,
                exposure=100,
                last_trade_age_days=1,
                concentration=1.0,
            ),
            _whale(
                "balanced",
                pnl=100,
                volume=100,
                trade_volume=100,
                exposure=100,
                last_trade_age_days=1,
                concentration=0.1,
            ),
        ],
        candidate_wallet_count=2,
        checked_wallet_count=2,
        generated_at=NOW,
        profile_version="test",
    )

    result = rank_trade_first_whales(whales)

    assert result.ranked_whales[0].whale.proxy_wallet == "balanced"


def test_rank_trade_first_whales_accepts_custom_weights() -> None:
    whales = Whales(
        whales=[
            _whale(
                "pnl-leader",
                pnl=100,
                volume=10,
                trade_volume=10,
                exposure=10,
                last_trade_age_days=5,
            ),
            _whale(
                "volume-leader",
                pnl=10,
                volume=100,
                trade_volume=100,
                exposure=100,
                last_trade_age_days=1,
            ),
        ],
        candidate_wallet_count=2,
        checked_wallet_count=2,
        generated_at=NOW,
        profile_version="test",
    )

    result = rank_trade_first_whales(
        whales,
        weights=TradeFirstRankingWeights(
            pnl=1,
            volume=0,
            trade_activity=0,
            recency=0,
            exposure=0,
            concentration_penalty=0,
            bottom_cut_percentile=0,
        ),
    )

    assert result.ranked_whales[0].whale.proxy_wallet == "pnl-leader"
