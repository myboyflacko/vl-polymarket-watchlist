from datetime import UTC, datetime
from typing import Any


def to_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(value: Any) -> datetime | None:
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


def row_timestamp(row: dict[str, Any]) -> datetime | None:
    return parse_timestamp(row.get("timestamp") or row.get("createdAt"))


def is_condition_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    if len(value) != 66 or not value.startswith("0x"):
        return False

    try:
        int(value[2:], 16)
    except ValueError:
        return False

    return True
