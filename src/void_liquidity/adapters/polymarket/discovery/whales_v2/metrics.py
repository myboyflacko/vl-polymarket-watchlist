from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from void_liquidity.adapters.polymarket.discovery.whales_v2.domain import (
    CollectionQuality,
    ExposureMetrics,
    MarketMetrics,
    TradeMetrics,
)
from void_liquidity.adapters.polymarket.discovery.whales_v2.helpers import (
    is_condition_id,
    row_timestamp,
    to_float,
)


def aggregate_trades(
    *,
    trades: list[dict[str, Any]],
    now: datetime,
    trade_window_days: int,
    recent_window_days: int,
    trades_complete: bool,
    trades_sort_order: str,
    invalid_trade_row_count: int,
) -> tuple[TradeMetrics, MarketMetrics, CollectionQuality, list[str]]:
    window_start = now - timedelta(days=trade_window_days)
    recent_start = now - timedelta(days=recent_window_days)
    market_volumes: dict[str, float] = defaultdict(float)
    newest_trade_at: datetime | None = None
    trade_count_30d = 0
    trade_count_7d = 0
    trade_volume_30d = 0.0
    trade_volume_7d = 0.0
    buy_volume_30d = 0.0
    sell_volume_30d = 0.0

    for trade in trades:
        timestamp = row_timestamp(trade)
        if timestamp is None:
            continue

        if newest_trade_at is None or timestamp > newest_trade_at:
            newest_trade_at = timestamp

        if timestamp < window_start:
            continue

        notional = to_float(trade.get("price")) * to_float(trade.get("size"))
        trade_count_30d += 1
        trade_volume_30d += notional

        condition_id = trade.get("conditionId")
        if is_condition_id(condition_id):
            market_volumes[condition_id] += notional

        side = trade.get("side")
        if side == "BUY":
            buy_volume_30d += notional
        elif side == "SELL":
            sell_volume_30d += notional

        if timestamp >= recent_start:
            trade_count_7d += 1
            trade_volume_7d += notional

    net_flow_30d = buy_volume_30d - sell_volume_30d
    largest_market_volume = max(market_volumes.values(), default=0.0)
    last_trade_age_days = (
        (now - newest_trade_at).total_seconds() / 86_400
        if newest_trade_at is not None
        else None
    )

    return (
        TradeMetrics(
            trade_count_30d=trade_count_30d,
            trade_count_7d=trade_count_7d,
            trade_volume_30d=trade_volume_30d,
            trade_volume_7d=trade_volume_7d,
            last_trade_at=newest_trade_at,
            last_trade_age_days=last_trade_age_days,
            avg_trade_size_30d=(
                trade_volume_30d / trade_count_30d if trade_count_30d else 0.0
            ),
            buy_volume_30d=buy_volume_30d,
            sell_volume_30d=sell_volume_30d,
            net_flow_30d=net_flow_30d,
            net_flow_ratio_30d=(
                net_flow_30d / trade_volume_30d if trade_volume_30d else None
            ),
            buy_sell_ratio_30d=(
                buy_volume_30d / sell_volume_30d if sell_volume_30d else None
            ),
        ),
        MarketMetrics(
            unique_markets_30d=len(market_volumes),
            market_concentration_30d=(
                largest_market_volume / trade_volume_30d if trade_volume_30d else 0.0
            ),
            largest_market_volume_30d=largest_market_volume,
        ),
        CollectionQuality(
            trades_complete=trades_complete,
            trades_sort_order="unknown" if trades_sort_order == "unknown" else "desc",
            invalid_trade_row_count=invalid_trade_row_count,
        ),
        sorted(market_volumes),
    )


def aggregate_current_positions(
    *,
    positions: list[dict[str, Any]],
    current_positions_complete: bool,
) -> tuple[ExposureMetrics, bool]:
    current_position_value = 0.0
    largest_position_value = 0.0

    for position in positions:
        current_value = to_float(position.get("currentValue"))
        current_position_value += current_value
        largest_position_value = max(largest_position_value, current_value)

    return (
        ExposureMetrics(
            current_position_value=current_position_value,
            open_position_count=len(positions),
            largest_position_value=largest_position_value,
            position_concentration=(
                largest_position_value / current_position_value
                if current_position_value
                else 0.0
            ),
        ),
        current_positions_complete,
    )
