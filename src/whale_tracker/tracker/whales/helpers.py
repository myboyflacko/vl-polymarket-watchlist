from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx

from whale_tracker.providers.polymarket.client import PolymarketDataClient
from whale_tracker.providers.polymarket.params.leaderboard.leaderboard import (
    LeaderboardParams,
)
from whale_tracker.providers.polymarket.params.profile.current_positions import (
    CurrentPositionsParams,
)
from whale_tracker.providers.polymarket.params.profile.trades import TradesParams
from whale_tracker.tracker.whales.domain import (
    CollectionQuality,
    ExposureMetrics,
    LeaderboardMetrics,
    MarketMetrics,
    TradeMetrics,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    WalletCollectionError,
    Whales,
)
from whale_tracker.tracker.whales.profiles import WhaleDiscoveryProfile


LeaderboardOrder = Literal["PNL", "VOL"]


@dataclass(frozen=True)
class _LeaderboardEntry:
    proxy_wallet: str
    row: dict[str, Any]


@dataclass(frozen=True)
class _Candidate:
    proxy_wallet: str
    pnl_entry: dict[str, Any] | None
    volume_entry: dict[str, Any] | None
    candidate_collection_complete: bool


@dataclass(frozen=True)
class _TradePageRows:
    rows: list[dict[str, Any]]
    complete: bool
    sort_order: Literal["desc", "unknown"]
    invalid_row_count: int


@dataclass(frozen=True)
class _CurrentPositionRows:
    rows: list[dict[str, Any]]
    complete: bool


@dataclass(frozen=True)
class _WalletCollectionResult:
    whale: Whale | None = None
    error: WalletCollectionError | None = None


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


def is_descending(values: list[datetime]) -> bool:
    return all(left >= right for left, right in zip(values, values[1:], strict=False))


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def collect_whales_from_polymarket(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    now: datetime,
) -> Whales:
    candidates = await _fetch_candidates(client=client, profile=profile)
    whales, collection_errors = await _collect_whales(
        client=client,
        profile=profile,
        candidates=candidates,
        now=now,
    )
    return Whales(
        whales=whales,
        candidate_wallet_count=len(candidates),
        checked_wallet_count=len(candidates),
        generated_at=now,
        profile_version=profile.profile_version,
        collection_errors=collection_errors,
    )


async def _fetch_candidates(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
) -> list[_Candidate]:
    pnl_entries, volume_entries = await asyncio.gather(
        _fetch_leaderboard(client=client, profile=profile, order_by="PNL"),
        _fetch_leaderboard(client=client, profile=profile, order_by="VOL"),
    )
    candidate_collection_complete = (
        len(pnl_entries) >= profile.wallet_count
        and len(volume_entries) >= profile.wallet_count
    )
    wallets = [*pnl_entries]

    for wallet in volume_entries:
        if wallet not in pnl_entries:
            wallets.append(wallet)

    return [
        _Candidate(
            proxy_wallet=wallet,
            pnl_entry=pnl_entries.get(wallet),
            volume_entry=volume_entries.get(wallet),
            candidate_collection_complete=candidate_collection_complete,
        )
        for wallet in wallets
    ]


async def _fetch_leaderboard(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    order_by: LeaderboardOrder,
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    offset = 0
    max_offset = 1000

    while len(entries) < profile.wallet_count and offset <= max_offset:
        params = LeaderboardParams(
            category=profile.leaderboard_category,
            timePeriod=profile.leaderboard_time_period,
            orderBy=order_by,
            limit=profile.leaderboard_limit,
            offset=offset,
        )
        page = await client.get_leaderboard(params)

        if not isinstance(page, list) or not page:
            break

        for row in page:
            entry = _parse_leaderboard_entry(row)
            if entry is None:
                continue

            entries.setdefault(entry.proxy_wallet, entry.row)

            if len(entries) >= profile.wallet_count:
                break

        if len(page) < params.limit:
            break

        offset += params.limit

    return entries


def _parse_leaderboard_entry(row: Any) -> _LeaderboardEntry | None:
    if not isinstance(row, dict):
        return None

    proxy_wallet = row.get("proxyWallet")
    if not isinstance(proxy_wallet, str):
        return None

    return _LeaderboardEntry(proxy_wallet=proxy_wallet, row=row)


async def _collect_whales(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    candidates: list[_Candidate],
    now: datetime,
) -> tuple[list[Whale], list[WalletCollectionError]]:
    whales: list[Whale] = []
    collection_errors: list[WalletCollectionError] = []

    for batch_start in range(0, len(candidates), profile.wallet_batch_size):
        batch = candidates[batch_start : batch_start + profile.wallet_batch_size]
        results = await asyncio.gather(
            *[
                _collect_whale_safely(
                    client=client,
                    profile=profile,
                    candidate=candidate,
                    now=now,
                )
                for candidate in batch
            ]
        )

        for result in results:
            if result.whale is not None:
                whales.append(result.whale)
            if result.error is not None:
                collection_errors.append(result.error)

    return whales, collection_errors


async def _collect_whale_safely(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    candidate: _Candidate,
    now: datetime,
) -> _WalletCollectionResult:
    try:
        return _WalletCollectionResult(
            whale=await _collect_whale(
                client=client,
                profile=profile,
                candidate=candidate,
                now=now,
            )
        )
    except _WalletStageError as exc:
        return _WalletCollectionResult(
            error=WalletCollectionError(
                proxy_wallet=candidate.proxy_wallet,
                stage=exc.stage,
                error_type=type(exc.__cause__ or exc).__name__,
                error=str(exc.__cause__ or exc),
            )
        )


async def _collect_whale(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    candidate: _Candidate,
    now: datetime,
) -> Whale:
    try:
        trade_rows = await _fetch_window_trades(
            client=client,
            profile=profile,
            proxy_wallet=candidate.proxy_wallet,
            now=now,
        )
    except Exception as exc:
        raise _WalletStageError("trades") from exc

    trade_metrics, market_metrics, quality, condition_ids = aggregate_trades(
        trades=trade_rows.rows,
        now=now,
        trade_window_days=profile.trade_window_days,
        recent_window_days=profile.recent_window_days,
        trades_complete=trade_rows.complete,
        trades_sort_order=trade_rows.sort_order,
        invalid_trade_row_count=trade_rows.invalid_row_count,
    )

    try:
        current_positions = await _fetch_current_positions(
            client=client,
            profile=profile,
            proxy_wallet=candidate.proxy_wallet,
            condition_ids=condition_ids,
        )
    except Exception as exc:
        raise _WalletStageError("current_positions") from exc

    exposure_metrics, current_positions_complete = aggregate_current_positions(
        positions=current_positions.rows,
        current_positions_complete=current_positions.complete,
    )
    quality = quality.model_copy(
        update={
            "current_positions_complete": current_positions_complete,
            "candidate_collection_complete": candidate.candidate_collection_complete,
        }
    )

    return Whale(
        identity=_identity(candidate=candidate, trades=trade_rows.rows),
        condition_ids_30d=condition_ids,
        metrics=WhaleMetrics(
            leaderboard=_leaderboard_metrics(candidate),
            trades=trade_metrics,
            markets=market_metrics,
            exposure=exposure_metrics,
            collection_quality=quality,
        ),
    )


def _identity(
    *,
    candidate: _Candidate,
    trades: list[dict[str, Any]],
) -> WhaleIdentity:
    row = candidate.pnl_entry or candidate.volume_entry or {}
    trade_row = trades[0] if trades else {}

    return WhaleIdentity(
        proxy_wallet=candidate.proxy_wallet,
        name=row.get("name") or trade_row.get("name"),
        pseudonym=row.get("pseudonym") or trade_row.get("pseudonym"),
        profile_image=row.get("profileImage") or trade_row.get("profileImage"),
    )


def _leaderboard_metrics(candidate: _Candidate) -> LeaderboardMetrics:
    pnl_entry = candidate.pnl_entry or {}
    volume_entry = candidate.volume_entry or {}
    candidate_source: Literal["pnl", "volume", "both"]

    if candidate.pnl_entry and candidate.volume_entry:
        candidate_source = "both"
    elif candidate.pnl_entry:
        candidate_source = "pnl"
    else:
        candidate_source = "volume"

    return LeaderboardMetrics(
        leaderboard_pnl_month=to_float(pnl_entry.get("pnl")),
        leaderboard_volume_month=to_float(volume_entry.get("vol")),
        pnl_rank=to_int(pnl_entry.get("rank")),
        volume_rank=to_int(volume_entry.get("rank")),
        candidate_source=candidate_source,
    )


async def _fetch_window_trades(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    proxy_wallet: str,
    now: datetime,
) -> _TradePageRows:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_count = 0
    sort_order: Literal["desc", "unknown"] = "desc"
    invalid_row_count = 0
    window_start = now - timedelta(days=profile.trade_window_days)

    while offset <= 10_000 and page_count < profile.max_trade_pages_per_wallet:
        params = TradesParams(
            user=proxy_wallet,
            limit=profile.trade_limit,
            offset=offset,
            takerOnly=profile.taker_only,
        )
        try:
            page = await client.get_trades(params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and offset > 0 and rows:
                return _TradePageRows(
                    rows=rows,
                    complete=False,
                    sort_order=sort_order,
                    invalid_row_count=invalid_row_count,
                )
            raise

        if not isinstance(page, list) or not page:
            return _TradePageRows(
                rows=rows,
                complete=True,
                sort_order=sort_order,
                invalid_row_count=invalid_row_count,
            )

        page_rows: list[dict[str, Any]] = []
        page_timestamps: list[datetime] = []

        for row in page:
            if not isinstance(row, dict):
                invalid_row_count += 1
                continue

            timestamp = row_timestamp(row)
            if timestamp is None:
                invalid_row_count += 1
                continue

            page_rows.append(row)
            page_timestamps.append(timestamp)

        if not is_descending(page_timestamps):
            sort_order = "unknown"

        rows.extend(page_rows)

        if sort_order == "desc" and page_timestamps and max(page_timestamps) < window_start:
            return _TradePageRows(
                rows=rows,
                complete=True,
                sort_order=sort_order,
                invalid_row_count=invalid_row_count,
            )

        if len(page) < params.limit:
            return _TradePageRows(
                rows=rows,
                complete=True,
                sort_order=sort_order,
                invalid_row_count=invalid_row_count,
            )

        offset += params.limit
        page_count += 1

    return _TradePageRows(
        rows=rows,
        complete=False,
        sort_order=sort_order,
        invalid_row_count=invalid_row_count,
    )


async def _fetch_current_positions(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    proxy_wallet: str,
    condition_ids: list[str],
) -> _CurrentPositionRows:
    if not condition_ids:
        return _CurrentPositionRows(rows=[], complete=True)

    rows: list[dict[str, Any]] = []
    complete = True

    for condition_id_chunk in chunks(
        condition_ids,
        profile.current_positions_market_chunk_size,
    ):
        result = await _fetch_current_position_chunk(
            client=client,
            profile=profile,
            proxy_wallet=proxy_wallet,
            condition_ids=condition_id_chunk,
        )
        rows.extend(result.rows)
        if not result.complete:
            complete = False

    return _CurrentPositionRows(rows=rows, complete=complete)


async def _fetch_current_position_chunk(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
    proxy_wallet: str,
    condition_ids: list[str],
) -> _CurrentPositionRows:
    rows: list[dict[str, Any]] = []
    offset = 0

    while offset <= 10_000:
        params = CurrentPositionsParams(
            user=proxy_wallet,
            market=condition_ids,
            limit=profile.current_positions_limit,
            offset=offset,
            sortBy="CURRENT",
            sortDirection="DESC",
        )
        try:
            page = await client.get_current_positions(params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise

            if len(condition_ids) == 1:
                return _CurrentPositionRows(rows=rows, complete=False)

            if offset > 0 and rows:
                return _CurrentPositionRows(rows=rows, complete=False)

            nested_rows: list[dict[str, Any]] = [*rows]
            complete = True
            for nested_chunk in chunks(condition_ids, max(1, len(condition_ids) // 2)):
                nested_result = await _fetch_current_position_chunk(
                    client=client,
                    profile=profile,
                    proxy_wallet=proxy_wallet,
                    condition_ids=nested_chunk,
                )
                nested_rows.extend(nested_result.rows)
                complete = complete and nested_result.complete

            return _CurrentPositionRows(rows=nested_rows, complete=complete)

        if not isinstance(page, list) or not page:
            return _CurrentPositionRows(rows=rows, complete=True)

        rows.extend(row for row in page if isinstance(row, dict))

        if len(page) < params.limit:
            return _CurrentPositionRows(rows=rows, complete=True)

        offset += params.limit

    return _CurrentPositionRows(rows=rows, complete=False)


class _WalletStageError(RuntimeError):
    def __init__(self, stage: Literal["trades", "current_positions"]) -> None:
        super().__init__(stage)
        self.stage = stage
