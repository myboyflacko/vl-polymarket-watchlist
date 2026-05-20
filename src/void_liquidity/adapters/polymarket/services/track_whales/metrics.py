from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from void_liquidity.adapters.polymarket.services.track_whales.helpers import (
    _parse_row_timestamp,
    _to_float,
)
from void_liquidity.adapters.polymarket.services.track_whales.schemas import (
    WhaleTrackingProfile,
)


def _aggregate_current_positions(
    current_positions: list[dict[str, Any]],
    is_complete: bool,
) -> dict[str, float | int | bool]:
    current_position_value = 0.0
    initial_position_value = 0.0
    open_cash_pnl = 0.0
    open_realized_pnl = 0.0
    largest_position_value = 0.0

    for position in current_positions:
        current_value = _to_float(position.get("currentValue"))
        current_position_value += current_value
        initial_position_value += _to_float(position.get("initialValue"))
        open_cash_pnl += _to_float(position.get("cashPnl"))
        open_realized_pnl += _to_float(position.get("realizedPnl"))
        largest_position_value = max(largest_position_value, current_value)

    return {
        "open_position_count": len(current_positions),
        "current_position_value": current_position_value,
        "initial_position_value": initial_position_value,
        "open_cash_pnl": open_cash_pnl,
        "open_realized_pnl": open_realized_pnl,
        "largest_position_value": largest_position_value,
        "current_positions_complete": is_complete,
    }


def _position_size(position: dict[str, Any]) -> float:
    for field_name in ("initialValue", "totalValue", "usdcSize", "currentValue"):
        size = _to_float(position.get(field_name))

        if size > 0:
            return size

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
    closed_positions_volume = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    largest_loss = 0.0

    for position in closed_positions:
        realized_pnl = _to_float(position.get("realizedPnl"))
        closed_positions_pnl += realized_pnl
        closed_positions_volume += _position_size(position)

        if realized_pnl > 0:
            wins += 1
            gross_profit += realized_pnl
        elif realized_pnl < 0:
            losses += 1
            loss = abs(realized_pnl)
            gross_loss += loss
            largest_loss = max(largest_loss, loss)
        else:
            breakevens += 1

    win_rate = wins / closed_trade_count if closed_trade_count else 0.0
    avg_pnl_per_trade = (
        closed_positions_pnl / closed_trade_count
        if closed_trade_count
        else 0.0
    )
    roi = (
        closed_positions_pnl / closed_positions_volume
        if closed_positions_volume
        else None
    )
    profit_factor = gross_profit / gross_loss if gross_loss else None
    avg_win = gross_profit / wins if wins else 0.0
    avg_loss = gross_loss / losses if losses else 0.0

    return {
        "closed_trade_count": closed_trade_count,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": win_rate,
        "closed_positions_pnl": closed_positions_pnl,
        "closed_positions_volume": closed_positions_volume,
        "roi": roi,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_loss": largest_loss,
        "avg_pnl_per_trade": avg_pnl_per_trade,
        "unknown_timestamp_count": unknown_timestamp_count,
        "closed_positions_complete": is_complete,
        "closed_positions_truncated": is_truncated,
    }


def _aggregate_activity(
    activity_rows: list[dict[str, Any]],
    is_complete: bool,
    window_start: datetime,
    last_activity_cutoff: datetime,
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
        "avg_trades_per_day_window": (
            trade_count_window / max((now - window_start).days, 1)
        ),
        "activity_volume_window": activity_volume_window,
        "activity_volume_7d": activity_volume_7d,
        "last_activity_at": (
            newest_activity_at.isoformat() if newest_activity_at else None
        ),
        "last_activity_age_days": last_activity_age_days,
        "last_activity_cutoff": last_activity_cutoff.isoformat(),
        "unknown_timestamp_count": unknown_timestamp_count,
        "activity_complete": is_complete,
        "activity_capped": not is_complete,
    }


def _leaderboard_metrics(
    proxy_wallet: str,
    pnl_entry: dict[str, Any] | None,
    vol_entry: dict[str, Any] | None,
    candidate_pool: dict[str, Any],
) -> dict[str, Any]:
    pnl_entry = pnl_entry or {}
    vol_entry = vol_entry or {}

    return {
        "candidate_pool_match": "core" in candidate_pool["matched_pools"],
        "candidate_pool_source": candidate_pool["source"],
        "matched_pools": candidate_pool["matched_pools"],
        "pnl_rank": pnl_entry.get("rank"),
        "vol_rank": vol_entry.get("rank"),
        "pnl": _to_float(pnl_entry.get("pnl")),
        "vol": _to_float(vol_entry.get("vol")),
        "pnl_leaderboard_wallet": pnl_entry.get("proxyWallet") == proxy_wallet,
        "vol_leaderboard_wallet": vol_entry.get("proxyWallet") == proxy_wallet,
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
        "min_win_rate": profile.filters.min_win_rate,
        "min_closed_positions_pnl": profile.filters.min_closed_positions_pnl,
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

    if closed_metrics["win_rate"] < profile.filters.min_win_rate:
        reasons.append("win_rate_below_min")

    if (
        closed_metrics["closed_positions_pnl"]
        <= profile.filters.min_closed_positions_pnl
    ):
        reasons.append("closed_positions_pnl_below_or_equal_min")

    if activity_metrics["trade_count_window"] < profile.activity.min_trade_count:
        reasons.append("activity_trade_count_below_min")

    last_activity_age_days = activity_metrics["last_activity_age_days"]

    if (
        last_activity_age_days is None
        or last_activity_age_days > profile.activity.last_activity_max_age_days
    ):
        reasons.append("last_activity_too_old")

    return reasons


def _build_payload(
    profile: WhaleTrackingProfile,
    whales: dict[str, dict[str, Any]],
    reject_summary: Counter[str],
    checked_wallet_count: int,
    candidate_wallet_count: int,
    candidate_pool_summary: Counter[str],
    generated_at: datetime,
) -> dict[str, Any]:
    return {
        "metadata": {
            "generated_at": generated_at.isoformat(),
            "mode": "fresh_discovery",
            "profile_version": profile.profile_version,
            "target_wallet_count": profile.target_wallet_count,
            "wallet_count": len(whales),
            "candidate_wallet_count": candidate_wallet_count,
            "candidate_pool_summary": dict(sorted(candidate_pool_summary.items())),
            "checked_wallet_count": checked_wallet_count,
            "reject_summary": dict(sorted(reject_summary.items())),
            "qualification_thresholds": _qualification_thresholds(profile),
            "candidate_pool": profile.candidate_pool.model_dump(),
        },
        "whales": whales,
    }
