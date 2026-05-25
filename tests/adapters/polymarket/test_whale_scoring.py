from typing import Any

from void_liquidity.adapters.polymarket.scoring import (
    filter_bottom_percentile_whales,
)


def _whale(
    *,
    current_position_value: float = 10_000,
    closed_trade_count: int = 50,
    closed_positions_pnl: float = 100,
    roi: float = 0.1,
    profit_factor: float = 2,
    activity_volume_window: float = 10_000,
    largest_win_share: float = 0.2,
) -> dict[str, Any]:
    return {
        "metrics": {
            "exposure": {
                "current_position_value": current_position_value,
            },
            "closed_positions": {
                "closed_trade_count": closed_trade_count,
                "closed_positions_pnl": closed_positions_pnl,
                "roi": roi,
                "profit_factor": profit_factor,
                "largest_win_share": largest_win_share,
            },
            "activity": {
                "activity_volume_window": activity_volume_window,
            },
        },
    }


def test_filter_bottom_percentile_whales_removes_bottom_quartile() -> None:
    whales = {
        "wallet-1": _whale(current_position_value=10),
        "wallet-2": _whale(current_position_value=20),
        "wallet-3": _whale(current_position_value=30),
        "wallet-4": _whale(current_position_value=40),
    }

    filtered = filter_bottom_percentile_whales(whales)

    assert list(filtered) == ["wallet-2", "wallet-3", "wallet-4"]


def test_filter_bottom_percentile_whales_removes_top_largest_win_share() -> None:
    whales = {
        "wallet-1": _whale(largest_win_share=0.1),
        "wallet-2": _whale(largest_win_share=0.2),
        "wallet-3": _whale(largest_win_share=0.3),
        "wallet-4": _whale(largest_win_share=0.4),
    }

    filtered = filter_bottom_percentile_whales(whales)

    assert list(filtered) == ["wallet-1", "wallet-2", "wallet-3"]


def test_filter_bottom_percentile_whales_recalculates_after_each_metric() -> None:
    whales = {
        "wallet-1": _whale(current_position_value=10, closed_trade_count=100),
        "wallet-2": _whale(current_position_value=20, closed_trade_count=10),
        "wallet-3": _whale(current_position_value=30, closed_trade_count=20),
        "wallet-4": _whale(current_position_value=40, closed_trade_count=30),
    }

    filtered = filter_bottom_percentile_whales(whales)

    assert list(filtered) == ["wallet-3", "wallet-4"]


def test_filter_bottom_percentile_whales_keeps_cutoff_ties() -> None:
    whales = {
        "wallet-1": _whale(current_position_value=10),
        "wallet-2": _whale(current_position_value=10),
        "wallet-3": _whale(current_position_value=10),
        "wallet-4": _whale(current_position_value=40),
    }

    filtered = filter_bottom_percentile_whales(whales)

    assert list(filtered) == ["wallet-1", "wallet-2", "wallet-3", "wallet-4"]


def test_filter_bottom_percentile_whales_keeps_single_or_empty_sets() -> None:
    single = {"wallet-1": _whale(current_position_value=10)}

    assert filter_bottom_percentile_whales({}) == {}
    assert filter_bottom_percentile_whales(single) == single
