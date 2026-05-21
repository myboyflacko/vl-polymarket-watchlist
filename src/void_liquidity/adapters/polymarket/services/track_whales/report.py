from collections import Counter
from datetime import datetime
from statistics import mean, median
from typing import Any

from void_liquidity.adapters.polymarket.services.track_whales.metrics import (
    _metric_quality_summary,
    _qualification_thresholds,
)
from void_liquidity.adapters.polymarket.services.track_whales.schemas import (
    WhaleTrackingProfile,
)


REPORT_METRICS = {
    "leaderboard": (
        "leaderboard_pnl",
        "leaderboard_volume",
    ),
    "exposure": (
        "open_position_count",
        "current_position_value",
        "largest_position_value",
        "position_concentration",
    ),
    "closed_positions": (
        "closed_trade_count",
        "closed_positions_pnl",
        "closed_positions_cost_basis",
        "roi",
        "profit_factor",
        "gross_profit",
        "gross_loss",
        "avg_win",
        "avg_loss",
        "largest_win",
        "largest_win_share",
        "largest_loss",
    ),
    "activity": (
        "trade_count_window",
        "trade_count_7d",
        "activity_volume_window",
        "activity_volume_7d",
        "last_activity_age_days",
    ),
}


MARGIN_METRICS = {
    "roi_margin": (
        "closed_positions",
        "roi",
        "min_roi",
        "above",
    ),
    "profit_factor_margin": (
        "closed_positions",
        "profit_factor",
        "min_profit_factor",
        "above",
    ),
    "largest_win_share_margin": (
        "closed_positions",
        "largest_win_share",
        "max_largest_win_share",
        "below",
    ),
    "current_position_value_margin": (
        "exposure",
        "current_position_value",
        "min_current_position_value",
        "above",
    ),
    "activity_volume_window_margin": (
        "activity",
        "activity_volume_window",
        "min_activity_volume",
        "above",
    ),
}


OUTLIER_METRICS = {
    "roi": ("closed_positions", "roi"),
    "profit_factor": ("closed_positions", "profit_factor"),
    "largest_win_share": ("closed_positions", "largest_win_share"),
    "position_concentration": ("exposure", "position_concentration"),
    "activity_volume_window": ("activity", "activity_volume_window"),
}


def _candidate_group(whale: dict[str, Any]) -> str:
    return whale["metrics"]["leaderboard"]["candidate_pool_source"]


def _metric_value(whale: dict[str, Any], section: str, name: str) -> float | int | None:
    value = whale["metrics"][section].get(name)

    if isinstance(value, bool) or not isinstance(value, int | float):
        return None

    return value


def _percentile(sorted_values: list[float | int], percentile: float) -> float | int | None:
    if not sorted_values:
        return None

    if len(sorted_values) == 1:
        return sorted_values[0]

    index = (len(sorted_values) - 1) * percentile
    lower_index = int(index)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = index - lower_index

    return (
        sorted_values[lower_index] * (1 - weight)
        + sorted_values[upper_index] * weight
    )


def _distribution(values: list[float | int]) -> dict[str, float | int | None]:
    sorted_values = sorted(values)

    if not sorted_values:
        return {
            "count": 0,
            "avg": None,
            "median": None,
            "p25": None,
            "p75": None,
            "min": None,
            "max": None,
        }

    return {
        "count": len(sorted_values),
        "avg": mean(sorted_values),
        "median": median(sorted_values),
        "p25": _percentile(sorted_values, 0.25),
        "p75": _percentile(sorted_values, 0.75),
        "min": sorted_values[0],
        "max": sorted_values[-1],
    }


def _accepted_metric_summary(
    whales: list[dict[str, Any]],
) -> dict[str, dict[str, float | int | None]]:
    summary: dict[str, dict[str, float | int | None]] = {}

    for section, metric_names in REPORT_METRICS.items():
        for metric_name in metric_names:
            values = [
                value
                for whale in whales
                if (value := _metric_value(whale, section, metric_name)) is not None
            ]
            summary[f"{section}.{metric_name}"] = _distribution(values)

    return summary


def _grouped_whales(whales: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for whale in whales.values():
        grouped.setdefault(_candidate_group(whale), []).append(whale)

    return grouped


def _acceptance_rate(accepted_count: int, checked_count: int) -> float | None:
    if checked_count == 0:
        return None

    return accepted_count / checked_count


def _candidate_funnel(
    whales: dict[str, dict[str, Any]],
    candidate_pool_summary: Counter[str],
    checked_group_summary: Counter[str],
    reject_summary: Counter[str],
    reject_group_summary: dict[str, Counter[str]],
) -> dict[str, Any]:
    accepted_group_summary = Counter(_candidate_group(whale) for whale in whales.values())
    groups = sorted(
        set(candidate_pool_summary)
        | set(checked_group_summary)
        | set(accepted_group_summary)
        | set(reject_group_summary)
    )

    return {
        "candidate_count": sum(candidate_pool_summary.values()),
        "checked_count": sum(checked_group_summary.values()),
        "accepted_count": len(whales),
        "acceptance_rate": _acceptance_rate(
            accepted_count=len(whales),
            checked_count=sum(checked_group_summary.values()),
        ),
        "candidate_pool_summary": dict(sorted(candidate_pool_summary.items())),
        "checked_summary": dict(sorted(checked_group_summary.items())),
        "accepted_summary": dict(sorted(accepted_group_summary.items())),
        "reject_summary": dict(sorted(reject_summary.items())),
        "by_group": {
            group: {
                "candidate_count": candidate_pool_summary.get(group, 0),
                "checked_count": checked_group_summary.get(group, 0),
                "accepted_count": accepted_group_summary.get(group, 0),
                "acceptance_rate": _acceptance_rate(
                    accepted_count=accepted_group_summary.get(group, 0),
                    checked_count=checked_group_summary.get(group, 0),
                ),
                "reject_summary": dict(
                    sorted(reject_group_summary.get(group, Counter()).items())
                ),
            }
            for group in groups
        },
    }


def _threshold_margins(
    whales: list[dict[str, Any]],
    thresholds: dict[str, Any],
) -> dict[str, dict[str, float | int | None]]:
    margins: dict[str, list[float | int]] = {name: [] for name in MARGIN_METRICS}

    for whale in whales:
        for margin_name, (section, metric_name, threshold_name, direction) in (
            MARGIN_METRICS.items()
        ):
            value = _metric_value(whale, section, metric_name)
            threshold = thresholds.get(threshold_name)

            if value is None or not isinstance(threshold, int | float):
                continue

            if direction == "below":
                margins[margin_name].append(threshold - value)
            else:
                margins[margin_name].append(value - threshold)

    return {
        margin_name: _distribution(values)
        for margin_name, values in margins.items()
    }


def _near_threshold_counts(
    whales: list[dict[str, Any]],
    thresholds: dict[str, Any],
    threshold_share: float = 0.10,
) -> dict[str, int]:
    counts = {name: 0 for name in MARGIN_METRICS}

    for whale in whales:
        for margin_name, (section, metric_name, threshold_name, direction) in (
            MARGIN_METRICS.items()
        ):
            value = _metric_value(whale, section, metric_name)
            threshold = thresholds.get(threshold_name)

            if value is None or not isinstance(threshold, int | float):
                continue

            tolerance = abs(threshold) * threshold_share

            if direction == "below":
                margin = threshold - value
            else:
                margin = value - threshold

            if 0 <= margin <= tolerance:
                counts[margin_name] += 1

    return counts


def _outlier_item(
    proxy_wallet: str,
    whale: dict[str, Any],
    section: str,
    metric_name: str,
) -> dict[str, Any]:
    return {
        "proxy_wallet": proxy_wallet,
        "user_name": whale["metadata"]["user_name"],
        "candidate_pool_source": _candidate_group(whale),
        metric_name: whale["metrics"][section][metric_name],
    }


def _outlier_summary(whales: dict[str, dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}

    for metric_name, (section, section_metric_name) in OUTLIER_METRICS.items():
        rows = [
            (proxy_wallet, whale)
            for proxy_wallet, whale in whales.items()
            if _metric_value(whale, section, section_metric_name) is not None
        ]
        rows = sorted(
            rows,
            key=lambda row: row[1]["metrics"][section][section_metric_name],
        )

        summary[metric_name] = {
            "bottom": [
                _outlier_item(proxy_wallet, whale, section, section_metric_name)
                for proxy_wallet, whale in rows[:5]
            ],
            "top": [
                _outlier_item(proxy_wallet, whale, section, section_metric_name)
                for proxy_wallet, whale in reversed(rows[-5:])
            ],
        }

    return summary


def build_report_payload(
    profile: WhaleTrackingProfile,
    whales: dict[str, dict[str, Any]],
    reject_summary: Counter[str],
    reject_group_summary: dict[str, Counter[str]],
    checked_wallet_count: int,
    checked_group_summary: Counter[str],
    candidate_wallet_count: int,
    candidate_pool_summary: Counter[str],
    generated_at: datetime,
    run_id: str,
) -> dict[str, Any]:
    thresholds = _qualification_thresholds(profile)
    grouped = _grouped_whales(whales)

    return {
        "metadata": {
            "run_id": run_id,
            "generated_at": generated_at.isoformat(),
            "mode": "fresh_discovery",
            "profile_version": profile.profile_version,
            "target_wallet_count": profile.target_wallet_count,
            "wallet_count": len(whales),
            "candidate_wallet_count": candidate_wallet_count,
            "checked_wallet_count": checked_wallet_count,
        },
        "profile": {
            "candidate_pool": profile.candidate_pool.model_dump(),
            "qualification_thresholds": thresholds,
        },
        "candidate_funnel": _candidate_funnel(
            whales=whales,
            candidate_pool_summary=candidate_pool_summary,
            checked_group_summary=checked_group_summary,
            reject_summary=reject_summary,
            reject_group_summary=reject_group_summary,
        ),
        "metric_quality_summary": _metric_quality_summary(whales),
        "accepted_metrics": {
            "overall": _accepted_metric_summary(list(whales.values())),
            "by_group": {
                group: _accepted_metric_summary(group_whales)
                for group, group_whales in sorted(grouped.items())
            },
        },
        "threshold_margin_summary": _threshold_margins(
            whales=list(whales.values()),
            thresholds=thresholds,
        ),
        "near_threshold_counts": _near_threshold_counts(
            whales=list(whales.values()),
            thresholds=thresholds,
        ),
        "outlier_summary": _outlier_summary(whales),
    }
