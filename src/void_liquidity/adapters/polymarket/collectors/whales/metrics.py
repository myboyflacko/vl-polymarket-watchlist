from datetime import datetime, timedelta
from typing import Any

from void_liquidity.adapters.polymarket.collectors.whales.helpers import (
    _parse_row_timestamp,
    _to_float,
)
from void_liquidity.adapters.polymarket.collectors.whales.schemas import (
    WhaleTrackingProfile,
)


def _aggregate_current_positions(
    current_positions: list[dict[str, Any]],
    is_complete: bool,
) -> dict[str, float | int | bool]:
    current_position_value = 0.0
    largest_position_value = 0.0

    for position in current_positions:
        current_value = _to_float(position.get("currentValue"))
        current_position_value += current_value
        largest_position_value = max(largest_position_value, current_value)

    position_concentration = (
        largest_position_value / current_position_value
        if current_position_value
        else 0.0
    )

    return {
        "open_position_count": len(current_positions),
        "current_position_value": current_position_value,
        "largest_position_value": largest_position_value,
        "position_concentration": position_concentration,
        "current_positions_complete": is_complete,
    }


def _position_cost_basis(position: dict[str, Any]) -> float:
    total_bought = _to_float(position.get("totalBought"))
    avg_price = _to_float(position.get("avgPrice"))

    if total_bought > 0 and avg_price > 0:
        return total_bought * avg_price

    average_price = _to_float(position.get("averagePrice"))

    if total_bought > 0 and average_price > 0:
        return total_bought * average_price

    return 0.0


def _aggregate_closed_positions(
    closed_positions: list[dict[str, Any]],
    is_complete: bool,
    unknown_timestamp_count: int,
    is_truncated: bool = False,
) -> dict[str, float | int | bool | None]:
    closed_trade_count = len(closed_positions)
    wins = 0
    losses = 0
    breakevens = 0
    closed_positions_pnl = 0.0
    closed_positions_cost_basis = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    largest_win = 0.0
    largest_loss = 0.0

    for position in closed_positions:
        realized_pnl = _to_float(position.get("realizedPnl"))
        closed_positions_pnl += realized_pnl
        closed_positions_cost_basis += _position_cost_basis(position)

        if realized_pnl > 0:
            wins += 1
            gross_profit += realized_pnl
            largest_win = max(largest_win, realized_pnl)
        elif realized_pnl < 0:
            losses += 1
            loss = abs(realized_pnl)
            gross_loss += loss
            largest_loss = max(largest_loss, loss)
        else:
            breakevens += 1

    win_rate = wins / closed_trade_count if closed_trade_count else 0.0
    roi = (
        closed_positions_pnl / closed_positions_cost_basis
        if closed_positions_cost_basis
        else None
    )
    profit_factor = gross_profit / gross_loss if gross_loss else None
    largest_win_share = largest_win / gross_profit if gross_profit else None
    avg_win = gross_profit / wins if wins else 0.0
    avg_loss = gross_loss / losses if losses else 0.0

    return {
        "closed_trade_count": closed_trade_count,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": win_rate,
        "closed_positions_pnl": closed_positions_pnl,
        "closed_positions_cost_basis": closed_positions_cost_basis,
        "roi": roi,
        "roi_available": roi is not None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_win_share": largest_win_share,
        "largest_loss": largest_loss,
        "unknown_timestamp_count": unknown_timestamp_count,
        "closed_positions_complete": is_complete,
        "closed_positions_truncated": is_truncated,
    }


def _aggregate_activity(
    activity_rows: list[dict[str, Any]],
    is_complete: bool,
    window_start: datetime,
    now: datetime,
) -> dict[str, float | int | str | None | bool]:
    trade_count_window = 0
    trade_count_7d = 0
    activity_volume_window = 0.0
    activity_volume_7d = 0.0
    unknown_timestamp_count = 0
    newest_activity_at: datetime | None = None
    seven_day_cutoff = now - timedelta(days=7)

    for row in activity_rows:
        row_timestamp = _parse_row_timestamp(row)

        if row_timestamp is None:
            unknown_timestamp_count += 1
            continue

        if newest_activity_at is None or row_timestamp > newest_activity_at:
            newest_activity_at = row_timestamp

        if row.get("type") == "TRADE":
            if row_timestamp >= window_start:
                trade_count_window += 1
                activity_volume_window += _to_float(row.get("usdcSize"))

            if row_timestamp >= seven_day_cutoff:
                trade_count_7d += 1
                activity_volume_7d += _to_float(row.get("usdcSize"))

    last_activity_age_days = (
        (now - newest_activity_at).total_seconds() / 86_400
        if newest_activity_at
        else None
    )

    return {
        "trade_count_window": trade_count_window,
        "trade_count_7d": trade_count_7d,
        "activity_volume_window": activity_volume_window,
        "activity_volume_7d": activity_volume_7d,
        "last_activity_at": (
            newest_activity_at.isoformat() if newest_activity_at else None
        ),
        "last_activity_age_days": last_activity_age_days,
        "unknown_timestamp_count": unknown_timestamp_count,
        "activity_complete": is_complete,
        "activity_capped": not is_complete,
    }


def _leaderboard_metrics(
    pnl_entry: dict[str, Any] | None,
    vol_entry: dict[str, Any] | None,
    candidate_pool: dict[str, Any],
) -> dict[str, Any]:
    pnl_entry = pnl_entry or {}
    vol_entry = vol_entry or {}

    return {
        "candidate_pool_source": candidate_pool["source"],
        "matched_pools": candidate_pool["matched_pools"],
        "pnl_rank": pnl_entry.get("rank"),
        "vol_rank": vol_entry.get("rank"),
        "leaderboard_pnl": _to_float(pnl_entry.get("pnl")),
        "leaderboard_volume": _to_float(vol_entry.get("vol")),
    }


def _build_candidate_pool(
    pnl_entries: dict[str, dict[str, Any]],
    vol_entries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates_by_wallet: dict[str, dict[str, Any]] = {}

    for proxy_wallet in pnl_entries:
        if _to_float(pnl_entries[proxy_wallet].get("pnl")) <= 0:
            continue

        matched_pools = ["pnl_top"]
        source = "pnl_specialist"

        if proxy_wallet in vol_entries:
            matched_pools = ["core", "pnl_top", "volume_top"]
            source = "core"

        candidates_by_wallet[proxy_wallet] = {
            "proxy_wallet": proxy_wallet,
            "source": source,
            "matched_pools": matched_pools,
        }

    for proxy_wallet, entry in vol_entries.items():
        if proxy_wallet in candidates_by_wallet:
            continue

        if _to_float(entry.get("pnl")) <= 0:
            continue

        candidates_by_wallet[proxy_wallet] = {
            "proxy_wallet": proxy_wallet,
            "source": "volume_profitable",
            "matched_pools": ["volume_top"],
        }

    return [
        *[
            candidate
            for candidate in candidates_by_wallet.values()
            if candidate["source"] == "core"
        ],
        *[
            candidate
            for candidate in candidates_by_wallet.values()
            if candidate["source"] == "pnl_specialist"
        ],
        *[
            candidate
            for candidate in candidates_by_wallet.values()
            if candidate["source"] == "volume_profitable"
        ],
    ]


def _qualification_thresholds(profile: WhaleTrackingProfile) -> dict[str, Any]:
    return {
        "min_current_position_value": profile.filters.min_current_position_value,
        "min_closed_trade_count": profile.filters.min_closed_trade_count,
        "min_closed_positions_pnl": profile.filters.min_closed_positions_pnl,
        "min_roi": profile.filters.min_roi,
        "min_profit_factor": profile.filters.min_profit_factor,
        "min_activity_volume": profile.filters.min_activity_volume,
        "max_largest_win_share": profile.filters.max_largest_win_share,
        "activity_trade_count_window_days": (
            profile.activity.trade_count_window_days
        ),
        "min_activity_trade_count": profile.activity.min_trade_count,
        "last_activity_max_age_days": profile.activity.last_activity_max_age_days,
    }


def _qualification_reasons(
    profile: WhaleTrackingProfile,
    exposure_metrics: dict[str, Any],
    closed_metrics: dict[str, Any],
    activity_metrics: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []

    if not exposure_metrics["current_positions_complete"]:
        reasons.append("current_positions_incomplete")

    if not closed_metrics["closed_positions_complete"]:
        reasons.append("closed_positions_incomplete")

    if (
        exposure_metrics["current_position_value"]
        < profile.filters.min_current_position_value
    ):
        reasons.append("current_position_value_below_min")

    if closed_metrics["closed_trade_count"] < profile.filters.min_closed_trade_count:
        reasons.append("closed_trade_count_below_min")

    if (
        closed_metrics["closed_positions_pnl"]
        <= profile.filters.min_closed_positions_pnl
    ):
        reasons.append("closed_positions_pnl_below_or_equal_min")

    roi = closed_metrics["roi"]

    if roi is None:
        reasons.append("roi_unavailable")
    elif roi <= profile.filters.min_roi:
        reasons.append("roi_below_or_equal_min")

    profit_factor = closed_metrics["profit_factor"]

    if (
        profit_factor is None
        or profit_factor < profile.filters.min_profit_factor
    ):
        reasons.append("profit_factor_below_min")

    largest_win_share = closed_metrics["largest_win_share"]

    if (
        largest_win_share is not None
        and largest_win_share > profile.filters.max_largest_win_share
    ):
        reasons.append("largest_win_share_above_max")

    activity_capped = activity_metrics["activity_capped"]

    if (
        activity_metrics["trade_count_window"] < profile.activity.min_trade_count
        and not activity_capped
    ):
        reasons.append("activity_trade_count_below_min")

    if (
        activity_metrics["activity_volume_window"]
        < profile.filters.min_activity_volume
    ):
        reasons.append("activity_volume_below_min")

    last_activity_age_days = activity_metrics["last_activity_age_days"]

    if (
        last_activity_age_days is None
        or last_activity_age_days > profile.activity.last_activity_max_age_days
    ):
        reasons.append("last_activity_too_old")

    return reasons


def _public_whale(whale: dict[str, Any]) -> dict[str, Any]:
    metrics = whale["metrics"]
    exposure = metrics["exposure"]
    closed_positions = metrics["closed_positions"]
    activity = metrics["activity"]

    return {
        "metadata": {
            "proxy_wallet": whale["metadata"]["proxy_wallet"],
            "user_name": whale["metadata"]["user_name"],
            "x_username": whale["metadata"]["x_username"],
            "verified_badge": whale["metadata"]["verified_badge"],
        },
        "metrics": {
            "leaderboard": metrics["leaderboard"],
            "exposure": {
                "open_position_count": exposure["open_position_count"],
                "current_position_value": exposure["current_position_value"],
                "largest_position_value": exposure["largest_position_value"],
                "position_concentration": exposure["position_concentration"],
            },
            "closed_positions": {
                "closed_trade_count": closed_positions["closed_trade_count"],
                "closed_positions_pnl": closed_positions["closed_positions_pnl"],
                "closed_positions_cost_basis": (
                    closed_positions["closed_positions_cost_basis"]
                ),
                "roi": closed_positions["roi"],
                "roi_available": closed_positions["roi_available"],
                "profit_factor": closed_positions["profit_factor"],
                "gross_profit": closed_positions["gross_profit"],
                "gross_loss": closed_positions["gross_loss"],
                "avg_win": closed_positions["avg_win"],
                "avg_loss": closed_positions["avg_loss"],
                "largest_win": closed_positions["largest_win"],
                "largest_win_share": closed_positions["largest_win_share"],
                "largest_loss": closed_positions["largest_loss"],
            },
            "activity": {
                "trade_count_window": activity["trade_count_window"],
                "trade_count_7d": activity["trade_count_7d"],
                "activity_volume_window": activity["activity_volume_window"],
                "activity_volume_7d": activity["activity_volume_7d"],
                "last_activity_at": activity["last_activity_at"],
                "last_activity_age_days": activity["last_activity_age_days"],
                "activity_complete": activity["activity_complete"],
                "activity_capped": activity["activity_capped"],
            },
        },
    }


def _metric_quality_summary(whales: dict[str, dict[str, Any]]) -> dict[str, int]:
    closed_metrics = [
        whale["metrics"]["closed_positions"] for whale in whales.values()
    ]
    activity_metrics = [whale["metrics"]["activity"] for whale in whales.values()]

    return {
        "roi_unavailable_count": sum(
            not metrics["roi_available"] for metrics in closed_metrics
        ),
        "activity_capped_count": sum(
            metrics["activity_capped"] for metrics in activity_metrics
        ),
        "closed_positions_truncated_count": sum(
            metrics.get("closed_positions_truncated", False)
            for metrics in closed_metrics
        ),
    }


def _build_payload(
    whales: dict[str, dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    return {
        "metadata": {
            "run_id": run_id,
        },
        "whales": {
            proxy_wallet: _public_whale(whale)
            for proxy_wallet, whale in whales.items()
        },
    }
