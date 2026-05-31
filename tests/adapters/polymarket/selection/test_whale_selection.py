from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.discovery.whales.domain import (
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
from void_liquidity.adapters.polymarket.discovery.whales.profiles import (
    TradeFirstRankingProfile,
)
from void_liquidity.adapters.polymarket.selection.whales import (
    selection as selection_module,
)
from void_liquidity.adapters.polymarket.selection.whales.selection import (
    list_selected_whale_wallets,
    select_trade_first_whales,
)


NOW = datetime(2026, 5, 31, tzinfo=UTC)


def test_select_trade_first_whales_returns_empty_ranking_without_db_whales(
    monkeypatch,
) -> None:
    monkeypatch.setattr(selection_module, "list_latest_whales", lambda: _whales([]))

    result = select_trade_first_whales()

    assert result.ranked_whales == []
    assert result.removed_whales == []


def test_select_trade_first_whales_ranks_latest_db_whales(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        selection_module,
        "list_latest_whales",
        lambda: _whales(
            [
                _whale("wallet-low", pnl=10, volume=10, exposure=10),
                _whale("wallet-high", pnl=100, volume=100, exposure=100),
            ]
        ),
    )

    result = select_trade_first_whales(
        profile=TradeFirstRankingProfile(bottom_cut_percentile=0),
    )

    assert [ranked.whale.proxy_wallet for ranked in result.ranked_whales] == [
        "wallet-high",
        "wallet-low",
    ]
    assert result.removed_whales == []


def test_list_selected_whale_wallets_returns_ranked_wallets(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        selection_module,
        "list_latest_whales",
        lambda: _whales(
            [
                _whale("wallet-low", pnl=10, volume=10, exposure=10),
                _whale("wallet-high", pnl=100, volume=100, exposure=100),
            ]
        ),
    )

    wallets = list_selected_whale_wallets(
        profile=TradeFirstRankingProfile(bottom_cut_percentile=0),
    )

    assert wallets == ["wallet-high", "wallet-low"]


def _whales(whales: list[Whale]) -> Whales:
    return Whales(
        whales=whales,
        candidate_wallet_count=len(whales),
        checked_wallet_count=len(whales),
        generated_at=NOW,
        profile_version="test",
    )


def _whale(
    proxy_wallet: str,
    *,
    pnl: float,
    volume: float,
    exposure: float,
) -> Whale:
    return Whale(
        identity=WhaleIdentity(proxy_wallet=proxy_wallet),
        metrics=WhaleMetrics(
            leaderboard=LeaderboardMetrics(
                leaderboard_pnl_month=pnl,
                leaderboard_volume_month=volume,
                candidate_source="both",
            ),
            trades=TradeMetrics(trade_volume_30d=volume),
            markets=MarketMetrics(),
            exposure=ExposureMetrics(current_position_value=exposure),
            collection_quality=CollectionQuality(),
        ),
    )
