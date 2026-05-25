from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal


PercentileDirection = Literal["bottom", "top"]
WhaleScoringMethod = Callable[
    [dict[str, dict[str, Any]]],
    dict[str, dict[str, Any]],
]

DEFAULT_WHALE_SCORING_METHOD = "percentile_v1"
RANKING_CRITERIA: tuple[tuple[str, str, PercentileDirection], ...] = (
    ("exposure", "current_position_value", "bottom"),
    ("closed_positions", "closed_trade_count", "bottom"),
    ("closed_positions", "closed_positions_pnl", "bottom"),
    ("closed_positions", "roi", "bottom"),
    ("closed_positions", "profit_factor", "bottom"),
    ("activity", "activity_volume_window", "bottom"),
    ("closed_positions", "largest_win_share", "top"),
)


def filter_bottom_percentile_whales(
    whales: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    ranked_whales = whales

    for section, metric_name, direction in RANKING_CRITERIA:
        if len(ranked_whales) < 2:
            break

        ranked_whales = _filter_metric_percentile(
            whales=ranked_whales,
            section=section,
            metric_name=metric_name,
            direction=direction,
        )

    return ranked_whales


WHALE_SCORING_METHODS: dict[str, WhaleScoringMethod] = {
    DEFAULT_WHALE_SCORING_METHOD: filter_bottom_percentile_whales,
}


def resolve_whale_scoring_method(method_name: str) -> WhaleScoringMethod:
    try:
        return WHALE_SCORING_METHODS[method_name]
    except KeyError as exc:
        available_methods = ", ".join(sorted(WHALE_SCORING_METHODS))
        raise ValueError(
            f"Unknown whale scoring method {method_name!r}. "
            f"Available methods: {available_methods}",
        ) from exc


def _filter_metric_percentile(
    whales: dict[str, dict[str, Any]],
    section: str,
    metric_name: str,
    direction: PercentileDirection,
) -> dict[str, dict[str, Any]]:
    values = [
        value
        for whale in whales.values()
        if (value := _metric_value(whale, section, metric_name)) is not None
    ]

    if len(values) < 2:
        return whales

    cutoff = _percentile(sorted(values), 0.75 if direction == "top" else 0.25)

    if direction == "top":
        return {
            proxy_wallet: whale
            for proxy_wallet, whale in whales.items()
            if (
                value := _metric_value(whale, section, metric_name)
            ) is None or value <= cutoff
        }

    return {
        proxy_wallet: whale
        for proxy_wallet, whale in whales.items()
        if (
            value := _metric_value(whale, section, metric_name)
        ) is None or value >= cutoff
    }


def _metric_value(
    whale: dict[str, Any],
    section: str,
    metric_name: str,
) -> float | int | None:
    value = whale["metrics"][section].get(metric_name)

    if isinstance(value, bool) or not isinstance(value, int | float):
        return None

    return value


def _percentile(sorted_values: list[float | int], percentile: float) -> float | int:
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
