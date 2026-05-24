from datetime import UTC, datetime
from typing import Any, Literal

from void_liquidity.adapters.polymarket.api.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    LeaderboardParams,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.schemas import (
    WhaleTrackingProfile,
)


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _field_le(model: type, field_name: str, default: int) -> int:
    field = model.model_fields[field_name]

    for metadata in field.metadata:
        le = getattr(metadata, "le", None)

        if le is not None:
            return int(le)

    return default


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, int | float):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=UTC)

    if isinstance(value, str):
        normalized_value = value.replace("Z", "+00:00")

        try:
            parsed = datetime.fromisoformat(normalized_value)
        except ValueError:
            try:
                timestamp = float(value)
            except ValueError:
                return None

            timestamp = timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
            return datetime.fromtimestamp(timestamp, tz=UTC)

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)

        return parsed.astimezone(UTC)

    return None


def _parse_row_timestamp(row: dict[str, Any]) -> datetime | None:
    value = (
        row.get("timestamp")
        or row.get("createdAt")
        or row.get("updatedAt")
        or row.get("closedAt")
    )
    return _parse_timestamp(value)


def _unix_seconds(value: datetime) -> int:
    return int(value.timestamp())


def _build_leaderboard_params(
    profile: WhaleTrackingProfile,
    order_by: Literal["PNL", "VOL"],
    offset: int,
) -> LeaderboardParams:
    return LeaderboardParams(
        category=profile.candidate_pool.category,
        timePeriod=profile.candidate_pool.time_period,
        orderBy=order_by,
        limit=profile.candidate_pool.leaderboard_limit,
        offset=offset,
    )


def _build_current_positions_params(
    profile: WhaleTrackingProfile,
    proxy_wallet: str,
    offset: int,
) -> CurrentPositionsParams:
    return CurrentPositionsParams(
        user=proxy_wallet,
        limit=profile.current_positions.limit,
        offset=offset,
        sortBy=profile.current_positions.sort_by,
        sortDirection=profile.current_positions.sort_direction,
    )


def _build_closed_positions_params(
    profile: WhaleTrackingProfile,
    proxy_wallet: str,
    offset: int,
) -> ClosedPositionsParams:
    return ClosedPositionsParams(
        user=proxy_wallet,
        limit=profile.closed_positions.limit,
        offset=offset,
        sortBy=profile.closed_positions.sort_by,
        sortDirection=profile.closed_positions.sort_direction,
    )


def _build_activity_params(
    profile: WhaleTrackingProfile,
    proxy_wallet: str,
    offset: int,
    start: datetime,
    end: datetime,
) -> ActivityParams:
    return ActivityParams(
        user=proxy_wallet,
        type=profile.activity.type,
        start=_unix_seconds(start),
        end=_unix_seconds(end),
        limit=profile.activity.limit,
        offset=offset,
        sortBy=profile.activity.sort_by,
        sortDirection=profile.activity.sort_direction,
    )
