import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from void_liquidity.adapters.polymarket.api import (
    get_closed_positions,
    get_current_positions,
    get_leaderboard,
)
from void_liquidity.adapters.polymarket.api.profile import PolymarketRateLimitError
from void_liquidity.adapters.polymarket.client import HTTPClient
from void_liquidity.adapters.polymarket.params import (
    ClosedPositionsParams,
    CurrentPositionsParams,
    LeaderboardParams,
)
from void_liquidity.settings import Settings


settings = Settings()
whale_tracker_settings = settings.whale_tracker

TARGET_WHALE_COUNT = whale_tracker_settings.target_count
LOOKBACK_DAYS = whale_tracker_settings.lookback_days
MIN_TRADE_COUNT = whale_tracker_settings.min_trade_count
MIN_WIN_RATE = whale_tracker_settings.min_win_rate
MIN_LEADERBOARD_VOLUME = whale_tracker_settings.min_leaderboard_volume
MIN_CURRENT_POSITION_VALUE = whale_tracker_settings.min_current_position_value
MAX_CLOSED_POSITIONS_PER_WALLET = (
    whale_tracker_settings.max_closed_positions_per_wallet
)
WALLET_BATCH_SIZE = whale_tracker_settings.batch_size
DEFAULT_WHALES_OUTPUT_PATH = Path(whale_tracker_settings.output_path)

DEFAULT_LEADERBOARD_PARAMS = LeaderboardParams(
    timePeriod=whale_tracker_settings.leaderboard_time_period,
    orderBy=whale_tracker_settings.leaderboard_order_by,
    limit=whale_tracker_settings.leaderboard_limit,
)
DEFAULT_CLOSED_POSITIONS_PARAMS = ClosedPositionsParams(
    user="0x0000000000000000000000000000000000000000",
    limit=whale_tracker_settings.closed_positions_limit,
    sortBy=whale_tracker_settings.closed_positions_sort_by,
    sortDirection=whale_tracker_settings.closed_positions_sort_direction,
)
DEFAULT_CURRENT_POSITIONS_PARAMS = CurrentPositionsParams(
    user="0x0000000000000000000000000000000000000000",
    limit=500,
    sortBy="CURRENT",
    sortDirection="DESC",
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


def _parse_position_timestamp(position: dict[str, Any]) -> datetime | None:
    value = (
        position.get("timestamp")
        or position.get("createdAt")
        or position.get("updatedAt")
        or position.get("closedAt")
    )

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


def _build_leaderboard_params(
    base_params: LeaderboardParams,
    offset: int,
) -> LeaderboardParams:
    if offset > _field_le(LeaderboardParams, "offset", default=1000):
        raise ValueError("leaderboard offset exceeds params limit")

    return base_params.model_copy(
        update={
            "offset": offset,
            "user": None,
            "userName": None,
        }
    )


def _build_wallet_leaderboard_params(
    proxy_wallet: str,
    base_params: LeaderboardParams,
) -> LeaderboardParams:
    return base_params.model_copy(
        update={
            "limit": 1,
            "offset": 0,
            "user": proxy_wallet,
            "userName": None,
        }
    )


def _build_closed_positions_params(
    proxy_wallet: str,
    offset: int,
    base_params: ClosedPositionsParams | None,
) -> ClosedPositionsParams:
    if base_params:
        return base_params.model_copy(
            update={
                "user": proxy_wallet,
                "offset": offset,
            }
        )

    return DEFAULT_CLOSED_POSITIONS_PARAMS.model_copy(
        update={
            "user": proxy_wallet,
            "offset": offset,
        }
    )


def _build_current_positions_params(
    proxy_wallet: str,
    offset: int,
    base_params: CurrentPositionsParams | None,
) -> CurrentPositionsParams:
    if base_params:
        return base_params.model_copy(
            update={
                "user": proxy_wallet,
                "offset": offset,
            }
        )

    return DEFAULT_CURRENT_POSITIONS_PARAMS.model_copy(
        update={
            "user": proxy_wallet,
            "offset": offset,
        }
    )


def _closed_positions_cutoff(leaderboard_params: LeaderboardParams) -> datetime:
    now = datetime.now(UTC)

    if leaderboard_params.timePeriod == "MONTH":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return now - timedelta(days=LOOKBACK_DAYS)


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


def _calculate_metrics(closed_positions: list[dict[str, Any]]) -> dict[str, float | int]:
    closed_trade_count = len(closed_positions)
    wins = 0
    losses = 0
    closed_positions_pnl = 0.0

    for position in closed_positions:
        realized_pnl = _to_float(position.get("realizedPnl"))
        closed_positions_pnl += realized_pnl

        if realized_pnl > 0:
            wins += 1
        elif realized_pnl < 0:
            losses += 1

    win_rate = wins / closed_trade_count if closed_trade_count else 0.0
    avg_pnl_per_trade = (
        closed_positions_pnl / closed_trade_count
        if closed_trade_count
        else 0.0
    )

    return {
        "closed_trade_count": closed_trade_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "closed_positions_pnl": closed_positions_pnl,
        "avg_pnl_per_trade": avg_pnl_per_trade,
    }


def _is_qualified_whale(metrics: dict[str, float | int]) -> bool:
    return (
        metrics["closed_trade_count"] >= MIN_TRADE_COUNT
        and metrics["win_rate"] >= MIN_WIN_RATE
    )


def _leaderboard_volume(leaderboard_entry: dict[str, Any]) -> float:
    return _to_float(leaderboard_entry.get("vol"))


def _leaderboard_pnl(whale: dict[str, Any]) -> float:
    leaderboard = whale.get("leaderboard") or whale.get("leaderboard_entry")

    if not isinstance(leaderboard, dict):
        return 0.0

    return _to_float(leaderboard.get("pnl"))


def _rank_whales(
    whales: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    ranked_whales = sorted(
        whales.values(),
        key=_leaderboard_pnl,
        reverse=True,
    )[:TARGET_WHALE_COUNT]

    for rank, whale in enumerate(ranked_whales, start=1):
        whale["rank"] = rank

    return {
        whale["proxy_wallet"]: whale
        for whale in ranked_whales
    }


def _build_whale_entry(
    proxy_wallet: str,
    leaderboard_entry: dict[str, Any],
    closed_positions: list[dict[str, Any]],
    current_positions: list[dict[str, Any]],
    current_position_metrics: dict[str, float | int | bool],
    metrics: dict[str, float | int],
) -> dict[str, Any]:
    return {
        "proxy_wallet": proxy_wallet,
        "user_name": leaderboard_entry.get("userName"),
        "leaderboard": leaderboard_entry,
        "closed_positions": closed_positions,
        "current_positions": current_positions,
        "current_position_metrics": current_position_metrics,
        "metrics": metrics,
        "rank": 0,
    }


def _normalize_cached_whale(
    proxy_wallet: str,
    whale: dict[str, Any],
) -> dict[str, Any]:
    leaderboard_entry = whale.get("leaderboard") or whale.get("leaderboard_entry")

    return {
        "proxy_wallet": whale.get("proxy_wallet") or proxy_wallet,
        "user_name": whale.get("user_name"),
        "leaderboard": leaderboard_entry if isinstance(leaderboard_entry, dict) else {},
        "current_position_metrics": (
            whale.get("current_position_metrics")
            if isinstance(whale.get("current_position_metrics"), dict)
            else {}
        ),
        "metrics": (
            whale.get("metrics")
            if isinstance(whale.get("metrics"), dict)
            else {}
        ),
        "rank": whale.get("rank", 0),
    }


def _to_json_whale(whale: dict[str, Any]) -> dict[str, Any]:
    leaderboard_entry = whale.get("leaderboard") or whale.get("leaderboard_entry")

    return {
        "proxy_wallet": whale.get("proxy_wallet"),
        "user_name": whale.get("user_name"),
        "rank": whale.get("rank", 0),
        "leaderboard_entry": (
            leaderboard_entry
            if isinstance(leaderboard_entry, dict)
            else {}
        ),
        "current_position_metrics": (
            whale.get("current_position_metrics")
            if isinstance(whale.get("current_position_metrics"), dict)
            else {}
        ),
        "metrics": (
            whale.get("metrics")
            if isinstance(whale.get("metrics"), dict)
            else {}
        ),
    }


async def _fetch_all_closed_positions(
    client: HTTPClient,
    proxy_wallet: str,
    closed_positions_params: ClosedPositionsParams | None,
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], bool]:
    closed_positions: list[dict[str, Any]] = []
    offset = 0

    max_offset = _field_le(ClosedPositionsParams, "offset", default=100000)
    page_limit = (
        closed_positions_params.limit
        if closed_positions_params
        else DEFAULT_CLOSED_POSITIONS_PARAMS.limit
    )

    while (
        offset <= max_offset
        and len(closed_positions) < MAX_CLOSED_POSITIONS_PER_WALLET
    ):
        params = _build_closed_positions_params(
            proxy_wallet=proxy_wallet,
            offset=offset,
            base_params=closed_positions_params,
        )
        print(
            "[closed_positions] "
            f"wallet={proxy_wallet} offset={params.offset} limit={params.limit}"
        )
        try:
            page = await get_closed_positions(
                client=client,
                params=params,
            )
        except PolymarketRateLimitError:
            print(
                "[closed_positions] "
                f"wallet={proxy_wallet} stop=rate_limited "
                f"total_positions={len(closed_positions)}"
            )
            return closed_positions, False

        if not isinstance(page, list) or not page:
            print(
                "[closed_positions] "
                f"wallet={proxy_wallet} stop=empty_or_invalid "
                f"total_positions={len(closed_positions)}"
            )
            return closed_positions, True

        reached_cutoff = False

        for position in page:
            if not isinstance(position, dict):
                continue

            position_timestamp = _parse_position_timestamp(position)

            if position_timestamp and position_timestamp < cutoff:
                reached_cutoff = True
                continue

            closed_positions.append(position)

        closed_positions = closed_positions[:MAX_CLOSED_POSITIONS_PER_WALLET]
        print(
            "[closed_positions] "
            f"wallet={proxy_wallet} received={len(page)} "
            f"total_positions={len(closed_positions)}"
        )

        if reached_cutoff:
            print(
                "[closed_positions] "
                f"wallet={proxy_wallet} stop=lookback_cutoff "
                f"cutoff={cutoff.isoformat()} "
                f"total_positions={len(closed_positions)}"
            )
            return closed_positions, True

        if len(page) < page_limit:
            print(
                "[closed_positions] "
                f"wallet={proxy_wallet} stop=last_page "
                f"total_positions={len(closed_positions)}"
            )
            return closed_positions, True

        if len(closed_positions) >= MAX_CLOSED_POSITIONS_PER_WALLET:
            print(
                "[closed_positions] "
                f"wallet={proxy_wallet} stop=max_positions "
                f"total_positions={len(closed_positions)}"
            )
            return closed_positions, True

        offset += page_limit

    print(
        "[closed_positions] "
        f"wallet={proxy_wallet} stop=max_offset "
        f"total_positions={len(closed_positions)}"
    )
    return closed_positions, True


async def _fetch_all_current_positions(
    client: HTTPClient,
    proxy_wallet: str,
    current_positions_params: CurrentPositionsParams | None,
) -> tuple[list[dict[str, Any]], bool]:
    current_positions: list[dict[str, Any]] = []
    offset = 0

    max_offset = _field_le(CurrentPositionsParams, "offset", default=10000)
    page_limit = (
        current_positions_params.limit
        if current_positions_params
        else DEFAULT_CURRENT_POSITIONS_PARAMS.limit
    )

    while offset <= max_offset:
        params = _build_current_positions_params(
            proxy_wallet=proxy_wallet,
            offset=offset,
            base_params=current_positions_params,
        )
        print(
            "[current_positions] "
            f"wallet={proxy_wallet} offset={params.offset} limit={params.limit}"
        )
        try:
            page = await get_current_positions(
                client=client,
                params=params,
            )
        except PolymarketRateLimitError:
            print(
                "[current_positions] "
                f"wallet={proxy_wallet} stop=rate_limited "
                f"total_positions={len(current_positions)}"
            )
            return current_positions, False

        if not isinstance(page, list) or not page:
            print(
                "[current_positions] "
                f"wallet={proxy_wallet} stop=empty_or_invalid "
                f"total_positions={len(current_positions)}"
            )
            return current_positions, True

        current_positions.extend(
            position
            for position in page
            if isinstance(position, dict)
        )
        print(
            "[current_positions] "
            f"wallet={proxy_wallet} received={len(page)} "
            f"total_positions={len(current_positions)}"
        )

        if len(page) < page_limit:
            print(
                "[current_positions] "
                f"wallet={proxy_wallet} stop=last_page "
                f"total_positions={len(current_positions)}"
            )
            return current_positions, True

        offset += page_limit

    print(
        "[current_positions] "
        f"wallet={proxy_wallet} stop=max_offset "
        f"total_positions={len(current_positions)}"
    )
    return current_positions, True


async def _fetch_wallet_leaderboard_entry(
    client: HTTPClient,
    proxy_wallet: str,
    leaderboard_params: LeaderboardParams,
) -> dict[str, Any] | None:
    params = _build_wallet_leaderboard_params(
        proxy_wallet=proxy_wallet,
        base_params=leaderboard_params,
    )
    leaderboard = await get_leaderboard(
        client=client,
        params=params,
    )

    if not isinstance(leaderboard, list) or not leaderboard:
        return None

    entry = leaderboard[0]

    if not isinstance(entry, dict):
        return None

    return entry


async def _validate_wallet(
    client: HTTPClient,
    proxy_wallet: str,
    leaderboard_entry: dict[str, Any],
    closed_positions_params: ClosedPositionsParams | None,
    current_positions_params: CurrentPositionsParams | None,
    cutoff: datetime,
) -> tuple[dict[str, Any] | None, str]:
    closed_positions, is_complete = await _fetch_all_closed_positions(
        client=client,
        proxy_wallet=proxy_wallet,
        closed_positions_params=closed_positions_params,
        cutoff=cutoff,
    )

    if not is_complete:
        return None, "incomplete_rate_limited"

    metrics = _calculate_metrics(closed_positions)
    leaderboard_volume = _leaderboard_volume(leaderboard_entry)

    if not _is_qualified_whale(metrics):
        reasons = []

        if metrics["closed_trade_count"] < MIN_TRADE_COUNT:
            reasons.append(f"trade_count<{MIN_TRADE_COUNT}")

        if metrics["win_rate"] < MIN_WIN_RATE:
            reasons.append(f"win_rate<{MIN_WIN_RATE}")

        return None, ",".join(reasons)

    if leaderboard_volume < MIN_LEADERBOARD_VOLUME:
        return None, f"leaderboard_volume<{MIN_LEADERBOARD_VOLUME}"

    current_positions, current_positions_complete = await _fetch_all_current_positions(
        client=client,
        proxy_wallet=proxy_wallet,
        current_positions_params=current_positions_params,
    )
    current_position_metrics = _aggregate_current_positions(
        current_positions=current_positions,
        is_complete=current_positions_complete,
    )
    current_position_value = _to_float(
        current_position_metrics.get("current_position_value")
    )

    if (
        current_positions_complete
        and current_position_value < MIN_CURRENT_POSITION_VALUE
    ):
        return None, f"current_position_value<{MIN_CURRENT_POSITION_VALUE}"

    return (
        _build_whale_entry(
            proxy_wallet=proxy_wallet,
            leaderboard_entry=leaderboard_entry,
            closed_positions=closed_positions,
            current_positions=current_positions,
            current_position_metrics=current_position_metrics,
            metrics=metrics,
        ),
        "qualified" if current_positions_complete else "qualified_current_incomplete",
    )


def load_whales_from_json(path: str | Path) -> dict[str, dict[str, Any]]:
    json_path = Path(path)

    if not json_path.exists():
        print(f"[json] load path={json_path} status=missing")
        return {}

    try:
        with json_path.open("r", encoding="utf-8") as json_file:
            payload = json.load(json_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[json] load path={json_path} status=invalid error={exc}")
        return {}

    whales = payload.get("whales") if isinstance(payload, dict) else None

    if not isinstance(whales, dict):
        print(f"[json] load path={json_path} status=no_whales")
        return {}

    print(f"[json] load path={json_path} rows={len(whales)}")
    return {
        proxy_wallet: _normalize_cached_whale(
            proxy_wallet=proxy_wallet,
            whale=whale,
        )
        for proxy_wallet, whale in whales.items()
        if isinstance(proxy_wallet, str) and isinstance(whale, dict)
    }


def _build_whales_payload(
    whales: dict[str, dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    json_whales = {
        proxy_wallet: _to_json_whale(whale)
        for proxy_wallet, whale in whales.items()
    }
    base_metadata = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "lookback_days": LOOKBACK_DAYS,
            "target_whale_count": TARGET_WHALE_COUNT,
            "min_trade_count": MIN_TRADE_COUNT,
            "min_win_rate": MIN_WIN_RATE,
            "min_leaderboard_volume": MIN_LEADERBOARD_VOLUME,
            "min_current_position_value": MIN_CURRENT_POSITION_VALUE,
            "wallet_count": len(json_whales),
        },
        "whales": json_whales,
    }

    if metadata:
        base_metadata["metadata"].update(metadata)

    return base_metadata


def write_whales_to_json(
    whales: dict[str, dict[str, Any]],
    path: str | Path,
    metadata: dict[str, Any] | None = None,
) -> None:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_whales_payload(whales=whales, metadata=metadata)

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, ensure_ascii=False, indent=2)

    print(f"[json] wrote path={json_path} rows={len(whales)}")


async def track_whales(
    closed_positions_params: ClosedPositionsParams | None = None,
    current_positions_params: CurrentPositionsParams | None = None,
    leaderboard_params: LeaderboardParams | None = None,
) -> dict[str, dict[str, Any]]:
    client = HTTPClient()
    whale_cache: dict[str, dict[str, Any]] = {}
    seen_wallets: set[str] = set()

    try:
        base_leaderboard_params = (
            leaderboard_params
            if leaderboard_params is not None
            else DEFAULT_LEADERBOARD_PARAMS.model_copy()
        )
        cutoff = _closed_positions_cutoff(base_leaderboard_params)
        max_leaderboard_offset = _field_le(LeaderboardParams, "offset", default=1000)
        print(
            "[track_whales] "
            f"start target={TARGET_WHALE_COUNT} "
            f"closed_positions_cutoff={cutoff.isoformat()} "
            f"min_trades={MIN_TRADE_COUNT} "
            f"min_win_rate={MIN_WIN_RATE} "
            f"min_leaderboard_volume={MIN_LEADERBOARD_VOLUME} "
            f"min_current_position_value={MIN_CURRENT_POSITION_VALUE} "
            f"leaderboard_time_period={base_leaderboard_params.timePeriod} "
            f"leaderboard_order_by={base_leaderboard_params.orderBy}"
        )
        offset = 0

        while (
            len(whale_cache) < TARGET_WHALE_COUNT
            and offset <= max_leaderboard_offset
        ):
            page_params = _build_leaderboard_params(
                base_params=base_leaderboard_params,
                offset=offset,
            )
            print(
                "[leaderboard] "
                f"offset={page_params.offset} limit={page_params.limit} "
                f"qualified_wallets={len(whale_cache)}"
            )
            leaderboard = await get_leaderboard(
                client=client,
                params=page_params,
            )

            if not isinstance(leaderboard, list) or not leaderboard:
                print(
                    "[leaderboard] "
                    f"offset={page_params.offset} stop=empty_or_invalid "
                    f"qualified_wallets={len(whale_cache)}"
                )
                break

            candidates: list[dict[str, Any]] = [
                entry
                for entry in leaderboard
                if isinstance(entry, dict) and entry.get("proxyWallet")
            ]
            proxy_wallets = [
                entry["proxyWallet"]
                for entry in candidates
                if entry["proxyWallet"] not in seen_wallets
            ]
            seen_wallets.update(proxy_wallets)
            print(
                "[leaderboard] "
                f"offset={page_params.offset} raw_entries={len(leaderboard)} "
                f"candidates={len(candidates)} new_wallets={len(proxy_wallets)}"
            )

            entries_by_wallet = {
                entry["proxyWallet"]: entry
                for entry in candidates
            }

            for batch_start in range(0, len(proxy_wallets), WALLET_BATCH_SIZE):
                batch = proxy_wallets[batch_start:batch_start + WALLET_BATCH_SIZE]
                print(
                    "[wallet_batch] "
                    f"start={batch_start} size={len(batch)} "
                    f"batch_size={WALLET_BATCH_SIZE}"
                )
                tasks = [
                    _validate_wallet(
                        client=client,
                        proxy_wallet=proxy_wallet,
                        leaderboard_entry=entries_by_wallet[proxy_wallet],
                        closed_positions_params=closed_positions_params,
                        current_positions_params=current_positions_params,
                        cutoff=cutoff,
                    )
                    for proxy_wallet in batch
                ]
                results = await asyncio.gather(*tasks)

                for proxy_wallet, result in zip(batch, results):
                    whale, status = result

                    if status == "incomplete_rate_limited":
                        print(
                            "[skipped] "
                            f"wallet={proxy_wallet} reason=incomplete_rate_limited "
                        )
                        continue

                    if not whale:
                        print(
                            "[rejected] "
                            f"wallet={proxy_wallet} reason={status}"
                        )
                        continue

                    metrics = whale["metrics"]
                    current_position_metrics = whale["current_position_metrics"]
                    whale_cache[proxy_wallet] = whale
                    print(
                        "[qualified] "
                        f"wallet={proxy_wallet} "
                        f"closed_trades={metrics['closed_trade_count']} "
                        f"wins={metrics['wins']} "
                        f"losses={metrics['losses']} "
                        f"win_rate={metrics['win_rate']:.2%} "
                        f"leaderboard_pnl={_leaderboard_pnl(whale):.2f} "
                        f"closed_positions_pnl={metrics['closed_positions_pnl']:.2f} "
                        f"avg_pnl_per_trade={metrics['avg_pnl_per_trade']:.2f} "
                        f"current_position_value={current_position_metrics['current_position_value']:.2f} "
                        f"open_positions={current_position_metrics['open_position_count']} "
                        f"qualified_wallets={len(whale_cache)}"
                    )

                if len(whale_cache) >= TARGET_WHALE_COUNT:
                    break

            offset += base_leaderboard_params.limit

        ranked_whales = sorted(
            whale_cache.values(),
            key=_leaderboard_pnl,
            reverse=True,
        )[:TARGET_WHALE_COUNT]

        for rank, whale in enumerate(ranked_whales, start=1):
            whale["rank"] = rank
            print(
                "[done] "
                f"rank={rank} wallet={whale['proxy_wallet']} "
                f"leaderboard_pnl={_leaderboard_pnl(whale):.2f} "
                f"avg_pnl_per_trade={whale['metrics']['avg_pnl_per_trade']:.2f} "
                f"win_rate={whale['metrics']['win_rate']:.2%} "
                f"closed_trades={whale['metrics']['closed_trade_count']}"
            )

        print(
            "[done] "
            f"qualified_wallets={len(ranked_whales)} "
            f"seen_wallets={len(seen_wallets)}"
        )

        return {
            whale["proxy_wallet"]: whale
            for whale in ranked_whales
        }

    finally:
        await client.close()


async def refresh_whales(
    path: str | Path = DEFAULT_WHALES_OUTPUT_PATH,
    closed_positions_params: ClosedPositionsParams | None = None,
    current_positions_params: CurrentPositionsParams | None = None,
    leaderboard_params: LeaderboardParams | None = None,
) -> dict[str, dict[str, Any]]:
    cached_whales = load_whales_from_json(path)
    refreshed_cache: dict[str, dict[str, Any]] = {}
    checked_wallets: set[str] = set()
    removed_wallet_count = 0
    added_wallet_count = 0
    kept_wallet_count = 0
    incomplete_wallet_count = 0
    client = HTTPClient()

    try:
        print(
            "[refresh_whales] "
            f"start cached_wallets={len(cached_whales)} "
            f"target={TARGET_WHALE_COUNT}"
        )
        base_leaderboard_params = (
            leaderboard_params
            if leaderboard_params is not None
            else DEFAULT_LEADERBOARD_PARAMS.model_copy()
        )
        cutoff = _closed_positions_cutoff(base_leaderboard_params)
        max_leaderboard_offset = _field_le(LeaderboardParams, "offset", default=1000)

        for proxy_wallet, cached_whale in cached_whales.items():
            checked_wallets.add(proxy_wallet)
            print(f"[refresh_existing] wallet={proxy_wallet}")

            leaderboard_entry = await _fetch_wallet_leaderboard_entry(
                client=client,
                proxy_wallet=proxy_wallet,
                leaderboard_params=base_leaderboard_params,
            )

            if leaderboard_entry is None:
                removed_wallet_count += 1
                print(
                    "[refresh_removed] "
                    f"wallet={proxy_wallet} reason=missing_leaderboard_entry"
                )
                continue

            whale, status = await _validate_wallet(
                client=client,
                proxy_wallet=proxy_wallet,
                leaderboard_entry=leaderboard_entry,
                closed_positions_params=closed_positions_params,
                current_positions_params=current_positions_params,
                cutoff=cutoff,
            )

            if whale:
                refreshed_cache[proxy_wallet] = whale
                kept_wallet_count += 1
                print(
                    "[refresh_kept] "
                    f"wallet={proxy_wallet} "
                    f"closed_trades={whale['metrics']['closed_trade_count']} "
                    f"win_rate={whale['metrics']['win_rate']:.2%} "
                    f"leaderboard_pnl={_leaderboard_pnl(whale):.2f} "
                    f"current_position_value={whale['current_position_metrics']['current_position_value']:.2f} "
                    f"open_positions={whale['current_position_metrics']['open_position_count']}"
                )
                continue

            if status == "incomplete_rate_limited":
                refreshed_cache[proxy_wallet] = cached_whale
                incomplete_wallet_count += 1
                print(
                    "[refresh_kept] "
                    f"wallet={proxy_wallet} reason=incomplete_rate_limited"
                )
                continue

            removed_wallet_count += 1
            print(f"[refresh_removed] wallet={proxy_wallet} reason={status}")

        offset = 0

        while (
            len(refreshed_cache) < TARGET_WHALE_COUNT
            and offset <= max_leaderboard_offset
        ):
            page_params = _build_leaderboard_params(
                base_params=base_leaderboard_params,
                offset=offset,
            )
            print(
                "[refresh_leaderboard] "
                f"offset={page_params.offset} limit={page_params.limit} "
                f"qualified_wallets={len(refreshed_cache)}"
            )
            leaderboard = await get_leaderboard(
                client=client,
                params=page_params,
            )

            if not isinstance(leaderboard, list) or not leaderboard:
                print(
                    "[refresh_leaderboard] "
                    f"offset={page_params.offset} stop=empty_or_invalid"
                )
                break

            candidates = [
                entry
                for entry in leaderboard
                if isinstance(entry, dict) and entry.get("proxyWallet")
            ]
            proxy_wallets = [
                entry["proxyWallet"]
                for entry in candidates
                if entry["proxyWallet"] not in refreshed_cache
                and entry["proxyWallet"] not in checked_wallets
            ]
            checked_wallets.update(proxy_wallets)
            entries_by_wallet = {
                entry["proxyWallet"]: entry
                for entry in candidates
            }

            for batch_start in range(0, len(proxy_wallets), WALLET_BATCH_SIZE):
                batch = proxy_wallets[batch_start:batch_start + WALLET_BATCH_SIZE]
                print(
                    "[refresh_batch] "
                    f"start={batch_start} size={len(batch)} "
                    f"batch_size={WALLET_BATCH_SIZE}"
                )
                tasks = [
                    _validate_wallet(
                        client=client,
                        proxy_wallet=proxy_wallet,
                        leaderboard_entry=entries_by_wallet[proxy_wallet],
                        closed_positions_params=closed_positions_params,
                        current_positions_params=current_positions_params,
                        cutoff=cutoff,
                    )
                    for proxy_wallet in batch
                ]
                results = await asyncio.gather(*tasks)

                for proxy_wallet, result in zip(batch, results):
                    whale, status = result

                    if not whale:
                        print(
                            "[refresh_candidate_rejected] "
                            f"wallet={proxy_wallet} reason={status}"
                        )
                        continue

                    refreshed_cache[proxy_wallet] = whale
                    added_wallet_count += 1
                    print(
                        "[refresh_added] "
                        f"wallet={proxy_wallet} "
                        f"closed_trades={whale['metrics']['closed_trade_count']} "
                        f"win_rate={whale['metrics']['win_rate']:.2%} "
                        f"leaderboard_pnl={_leaderboard_pnl(whale):.2f} "
                        f"current_position_value={whale['current_position_metrics']['current_position_value']:.2f} "
                        f"open_positions={whale['current_position_metrics']['open_position_count']} "
                        f"qualified_wallets={len(refreshed_cache)}"
                    )

                if len(refreshed_cache) >= TARGET_WHALE_COUNT:
                    break

            offset += base_leaderboard_params.limit

        ranked_whales = _rank_whales(refreshed_cache)
        write_whales_to_json(
            whales=ranked_whales,
            path=path,
            metadata={
                "refreshed_at": datetime.now(UTC).isoformat(),
                "mode": "refresh",
                "leaderboard_time_period": base_leaderboard_params.timePeriod,
                "leaderboard_order_by": base_leaderboard_params.orderBy,
                "closed_positions_cutoff": cutoff.isoformat(),
                "removed_wallet_count": removed_wallet_count,
                "added_wallet_count": added_wallet_count,
                "kept_wallet_count": kept_wallet_count,
                "incomplete_wallet_count": incomplete_wallet_count,
                "checked_wallet_count": len(checked_wallets),
            },
        )
        print(
            "[refresh_done] "
            f"wallets={len(ranked_whales)} "
            f"kept={kept_wallet_count} "
            f"added={added_wallet_count} "
            f"removed={removed_wallet_count} "
            f"incomplete={incomplete_wallet_count}"
        )

        return ranked_whales

    finally:
        await client.close()


if __name__ == "__main__":
    whales = asyncio.run(refresh_whales())
    print(f"[refresh_whales] returned_wallets={len(whales)}")
