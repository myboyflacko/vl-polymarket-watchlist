import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from void_liquidity.adapters.polymarket.api import (
    get_activity,
    get_closed_positions,
    get_current_positions,
    get_leaderboard,
)
from void_liquidity.adapters.polymarket.api.profile import PolymarketRateLimitError
from void_liquidity.adapters.polymarket.client import HTTPClient
from void_liquidity.adapters.polymarket.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    LeaderboardParams,
)
from void_liquidity.util.log import log_event


SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parents[4]
DEFAULT_PROFILE_PATH = SERVICE_DIR / "config" / "whale_tracking_profile.json"


class CandidatePoolConfig(BaseModel):
    category: str = "OVERALL"
    time_period: str = "MONTH"
    top_n: int = Field(default=250, ge=1)
    leaderboard_limit: int = Field(default=50, ge=1, le=50)


class CurrentPositionsConfig(BaseModel):
    limit: int = Field(default=500, ge=1, le=500)
    sort_by: str = "CURRENT"
    sort_direction: str = "DESC"


class ClosedPositionsConfig(BaseModel):
    window_days: int = Field(default=30, ge=1)
    limit: int = Field(default=50, ge=1, le=50)
    sort_by: str = "TIMESTAMP"
    sort_direction: str = "DESC"
    max_positions_per_wallet: int = Field(default=500, ge=1)


class ActivityConfig(BaseModel):
    trade_count_window_days: int = Field(default=30, ge=1)
    min_trade_count: int = Field(default=10, ge=0)
    last_activity_max_age_days: int = Field(default=7, ge=1)
    limit: int = Field(default=500, ge=1, le=500)
    sort_by: str = "TIMESTAMP"
    sort_direction: str = "DESC"
    type: list[str] = Field(default_factory=lambda: ["TRADE"])


class WhaleFilterConfig(BaseModel):
    min_current_position_value: float = Field(default=10_000.0, ge=0)
    min_closed_trade_count: int = Field(default=50, ge=1)
    min_win_rate: float = Field(default=0.70, ge=0, le=1)
    min_closed_positions_pnl: float = 0.0


class WhaleTrackingProfile(BaseModel):
    profile_version: str = "whale_tracking_v2"
    target_wallet_count: int = Field(default=50, ge=1)
    wallet_batch_size: int = Field(default=4, ge=1)
    output_path: str = (
        "src/void_liquidity/adapters/polymarket/services/data/"
        "polymarket_whales.json"
    )
    candidate_pool: CandidatePoolConfig = Field(default_factory=CandidatePoolConfig)
    current_positions: CurrentPositionsConfig = Field(
        default_factory=CurrentPositionsConfig,
    )
    closed_positions: ClosedPositionsConfig = Field(
        default_factory=ClosedPositionsConfig,
    )
    activity: ActivityConfig = Field(default_factory=ActivityConfig)
    filters: WhaleFilterConfig = Field(default_factory=WhaleFilterConfig)


def load_workflow_profile(
    path: str | Path = DEFAULT_PROFILE_PATH,
) -> WhaleTrackingProfile:
    profile_path = Path(path)

    with profile_path.open("r", encoding="utf-8") as profile_file:
        payload = json.load(profile_file)

    return WhaleTrackingProfile.model_validate(payload)


def _resolve_project_path(path: str | Path) -> Path:
    resolved_path = Path(path)

    if resolved_path.is_absolute():
        return resolved_path

    return PROJECT_ROOT / resolved_path


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


class WhaleTracker:
    def __init__(self, profile: WhaleTrackingProfile | None = None) -> None:
        self.profile = profile or load_workflow_profile()

    async def run(self) -> dict[str, dict[str, Any]]:
        client = HTTPClient()
        now = datetime.now(UTC)

        try:
            log_event(
                "info",
                "polymarket.track_whales.start",
                profile_version=self.profile.profile_version,
                target=self.profile.target_wallet_count,
            )
            pnl_entries, vol_entries, candidates, candidate_pool_summary = (
                await self._fetch_candidate_entries(client=client)
            )
            whales, reject_summary, checked_wallet_count = (
                await self._process_candidate_batches(
                    client=client,
                    candidates=candidates,
                    pnl_entries=pnl_entries,
                    vol_entries=vol_entries,
                    now=now,
                )
            )
            self._write_whales_to_json(
                whales=whales,
                reject_summary=reject_summary,
                checked_wallet_count=checked_wallet_count,
                candidate_wallet_count=len(candidates),
                candidate_pool_summary=candidate_pool_summary,
            )
            log_event(
                "info",
                "polymarket.track_whales.done",
                wallets=len(whales),
                checked=checked_wallet_count,
            )
            return whales

        finally:
            await client.close()

    async def _fetch_candidate_entries(
        self,
        client: HTTPClient,
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        list[dict[str, Any]],
        Counter[str],
    ]:
        pnl_entries = await self._fetch_leaderboard_top(
            client=client,
            order_by="PNL",
        )
        vol_entries = await self._fetch_leaderboard_top(
            client=client,
            order_by="VOL",
        )
        candidates = _build_candidate_pool(
            pnl_entries=pnl_entries,
            vol_entries=vol_entries,
        )
        candidate_pool_summary = Counter(
            candidate["source"] for candidate in candidates
        )
        log_event(
            "info",
            "polymarket.candidate_pool.built",
            pnl_wallets=len(pnl_entries),
            vol_wallets=len(vol_entries),
            candidates=len(candidates),
        )
        return pnl_entries, vol_entries, candidates, candidate_pool_summary

    async def _fetch_leaderboard_top(
        self,
        client: HTTPClient,
        order_by: Literal["PNL", "VOL"],
    ) -> dict[str, dict[str, Any]]:
        entries_by_wallet: dict[str, dict[str, Any]] = {}
        offset = 0
        max_offset = _field_le(LeaderboardParams, "offset", default=1000)

        while (
            len(entries_by_wallet) < self.profile.candidate_pool.top_n
            and offset <= max_offset
        ):
            params = _build_leaderboard_params(
                profile=self.profile,
                order_by=order_by,
                offset=offset,
            )
            log_event(
                "info",
                "polymarket.leaderboard.fetch",
                order_by=order_by,
                offset=params.offset,
                limit=params.limit,
            )
            page = await get_leaderboard(client=client, params=params)

            if not isinstance(page, list) or not page:
                log_event(
                    "info",
                    "polymarket.leaderboard.empty",
                    order_by=order_by,
                    offset=params.offset,
                    stop="empty_or_invalid",
                )
                break

            for entry in page:
                if not isinstance(entry, dict):
                    continue

                proxy_wallet = entry.get("proxyWallet")

                if (
                    isinstance(proxy_wallet, str)
                    and proxy_wallet not in entries_by_wallet
                ):
                    entries_by_wallet[proxy_wallet] = entry

                if len(entries_by_wallet) >= self.profile.candidate_pool.top_n:
                    break

            if len(page) < params.limit:
                break

            offset += params.limit

        log_event(
            "info",
            "polymarket.leaderboard.done",
            order_by=order_by,
            wallets=len(entries_by_wallet),
        )
        return entries_by_wallet

    async def _process_candidate_batches(
        self,
        client: HTTPClient,
        candidates: list[dict[str, Any]],
        pnl_entries: dict[str, dict[str, Any]],
        vol_entries: dict[str, dict[str, Any]],
        now: datetime,
    ) -> tuple[dict[str, dict[str, Any]], Counter[str], int]:
        whales: dict[str, dict[str, Any]] = {}
        reject_summary: Counter[str] = Counter()
        checked_wallet_count = 0

        for batch_start in range(
            0,
            len(candidates),
            self.profile.wallet_batch_size,
        ):
            if len(whales) >= self.profile.target_wallet_count:
                break

            batch = candidates[batch_start:batch_start + self.profile.wallet_batch_size]
            log_event(
                "info",
                "polymarket.wallet_batch.start",
                start=batch_start,
                size=len(batch),
                qualified_wallets=len(whales),
            )
            results = await asyncio.gather(
                *[
                    self._validate_candidate(
                        client=client,
                        candidate=candidate,
                        pnl_entry=pnl_entries.get(candidate["proxy_wallet"]),
                        vol_entry=vol_entries.get(candidate["proxy_wallet"]),
                        now=now,
                    )
                    for candidate in batch
                ]
            )

            for candidate, result in zip(batch, results):
                proxy_wallet = candidate["proxy_wallet"]
                checked_wallet_count += 1
                whale, reasons = result

                if not whale:
                    reject_summary.update(reasons)
                    log_event(
                        "info",
                        "polymarket.wallet.rejected",
                        wallet=proxy_wallet,
                        reasons=reasons,
                    )
                    continue

                whales[proxy_wallet] = whale
                log_event(
                    "info",
                    "polymarket.wallet.qualified",
                    wallet=proxy_wallet,
                    qualified_wallets=len(whales),
                )

                if len(whales) >= self.profile.target_wallet_count:
                    break

        return whales, reject_summary, checked_wallet_count

    async def _validate_candidate(
        self,
        client: HTTPClient,
        candidate: dict[str, Any],
        pnl_entry: dict[str, Any] | None,
        vol_entry: dict[str, Any] | None,
        now: datetime,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        proxy_wallet = candidate["proxy_wallet"]
        closed_cutoff = now - timedelta(days=self.profile.closed_positions.window_days)
        activity_window_start = now - timedelta(
            days=self.profile.activity.trade_count_window_days,
        )
        last_activity_cutoff = now - timedelta(
            days=self.profile.activity.last_activity_max_age_days,
        )
        activity_fetch_start = min(
            activity_window_start,
            last_activity_cutoff,
            now - timedelta(days=7),
        )

        current_positions, current_complete = await self._fetch_all_current_positions(
            client=client,
            proxy_wallet=proxy_wallet,
        )
        exposure_metrics = _aggregate_current_positions(
            current_positions=current_positions,
            is_complete=current_complete,
        )

        closed_positions, closed_complete, unknown_closed_timestamps, closed_truncated = (
            await self._fetch_all_closed_positions(
                client=client,
                proxy_wallet=proxy_wallet,
                cutoff=closed_cutoff,
            )
        )
        closed_metrics = _aggregate_closed_positions(
            closed_positions=closed_positions,
            is_complete=closed_complete,
            unknown_timestamp_count=unknown_closed_timestamps,
            is_truncated=closed_truncated,
        )

        activity_rows, activity_complete = await self._fetch_all_activity(
            client=client,
            proxy_wallet=proxy_wallet,
            start=activity_fetch_start,
            end=now,
        )
        activity_metrics = _aggregate_activity(
            activity_rows=activity_rows,
            is_complete=activity_complete,
            window_start=activity_window_start,
            last_activity_cutoff=last_activity_cutoff,
            now=now,
        )

        reasons = _qualification_reasons(
            profile=self.profile,
            exposure_metrics=exposure_metrics,
            closed_metrics=closed_metrics,
            activity_metrics=activity_metrics,
        )

        if reasons:
            return None, reasons

        identity_entry = pnl_entry or vol_entry or {}
        whale = {
            "metadata": {
                "proxy_wallet": proxy_wallet,
                "user_name": identity_entry.get("userName"),
                "x_username": identity_entry.get("xUsername"),
                "profile_image": identity_entry.get("profileImage"),
                "verified_badge": identity_entry.get("verifiedBadge"),
            },
            "metrics": {
                "leaderboard": _leaderboard_metrics(
                    proxy_wallet=proxy_wallet,
                    pnl_entry=pnl_entry,
                    vol_entry=vol_entry,
                    candidate_pool=candidate,
                ),
                "exposure": exposure_metrics,
                "closed_positions": {
                    **closed_metrics,
                    "window_days": self.profile.closed_positions.window_days,
                    "cutoff": closed_cutoff.isoformat(),
                },
                "activity": {
                    **activity_metrics,
                    "trade_count_window_days": (
                        self.profile.activity.trade_count_window_days
                    ),
                },
                "qualification": {
                    "passed": True,
                    "profile_version": self.profile.profile_version,
                    "thresholds": _qualification_thresholds(self.profile),
                },
            },
        }
        return whale, []

    async def _fetch_all_current_positions(
        self,
        client: HTTPClient,
        proxy_wallet: str,
    ) -> tuple[list[dict[str, Any]], bool]:
        current_positions: list[dict[str, Any]] = []
        offset = 0
        max_offset = _field_le(CurrentPositionsParams, "offset", default=10000)

        while offset <= max_offset:
            params = _build_current_positions_params(
                profile=self.profile,
                proxy_wallet=proxy_wallet,
                offset=offset,
            )
            log_event(
                "info",
                "polymarket.current_positions.fetch",
                wallet=proxy_wallet,
                offset=params.offset,
                limit=params.limit,
            )

            try:
                page = await get_current_positions(client=client, params=params)
            except PolymarketRateLimitError:
                return current_positions, False

            if not isinstance(page, list) or not page:
                return current_positions, True

            current_positions.extend(row for row in page if isinstance(row, dict))

            if len(page) < params.limit:
                return current_positions, True

            offset += params.limit

        return current_positions, True

    async def _fetch_all_closed_positions(
        self,
        client: HTTPClient,
        proxy_wallet: str,
        cutoff: datetime,
    ) -> tuple[list[dict[str, Any]], bool, int, bool]:
        closed_positions: list[dict[str, Any]] = []
        unknown_timestamp_count = 0
        offset = 0
        max_offset = _field_le(ClosedPositionsParams, "offset", default=100000)

        while (
            offset <= max_offset
            and len(closed_positions)
            < self.profile.closed_positions.max_positions_per_wallet
        ):
            params = _build_closed_positions_params(
                profile=self.profile,
                proxy_wallet=proxy_wallet,
                offset=offset,
            )
            log_event(
                "info",
                "polymarket.closed_positions.fetch",
                wallet=proxy_wallet,
                offset=params.offset,
                limit=params.limit,
            )

            try:
                page = await get_closed_positions(client=client, params=params)
            except PolymarketRateLimitError:
                return closed_positions, False, unknown_timestamp_count, False

            if not isinstance(page, list) or not page:
                return closed_positions, True, unknown_timestamp_count, False

            reached_cutoff = False

            for position in page:
                if not isinstance(position, dict):
                    continue

                position_timestamp = _parse_row_timestamp(position)

                if position_timestamp is None:
                    unknown_timestamp_count += 1
                    continue

                if position_timestamp < cutoff:
                    reached_cutoff = True
                    continue

                closed_positions.append(position)

            closed_positions = closed_positions[
                :self.profile.closed_positions.max_positions_per_wallet
            ]

            if reached_cutoff:
                return closed_positions, True, unknown_timestamp_count, False

            if len(page) < params.limit:
                return closed_positions, True, unknown_timestamp_count, False

            if (
                len(closed_positions)
                >= self.profile.closed_positions.max_positions_per_wallet
            ):
                return closed_positions, True, unknown_timestamp_count, True

            offset += params.limit

        return closed_positions, True, unknown_timestamp_count, False

    async def _fetch_all_activity(
        self,
        client: HTTPClient,
        proxy_wallet: str,
        start: datetime,
        end: datetime,
    ) -> tuple[list[dict[str, Any]], bool]:
        activity_rows: list[dict[str, Any]] = []
        offset = 0
        max_offset = _field_le(ActivityParams, "offset", default=3000)

        while offset <= max_offset:
            params = _build_activity_params(
                profile=self.profile,
                proxy_wallet=proxy_wallet,
                offset=offset,
                start=start,
                end=end,
            )
            log_event(
                "info",
                "polymarket.activity.fetch",
                wallet=proxy_wallet,
                offset=params.offset,
                limit=params.limit,
            )

            try:
                page = await get_activity(client=client, params=params)
            except PolymarketRateLimitError:
                return activity_rows, False

            if not isinstance(page, list) or not page:
                return activity_rows, True

            activity_rows.extend(row for row in page if isinstance(row, dict))

            if len(page) < params.limit:
                return activity_rows, True

            offset += params.limit

        return activity_rows, False

    def _write_whales_to_json(
        self,
        whales: dict[str, dict[str, Any]],
        reject_summary: Counter[str],
        checked_wallet_count: int,
        candidate_wallet_count: int,
        candidate_pool_summary: Counter[str] | None = None,
        path: str | Path | None = None,
    ) -> None:
        output_path = _resolve_project_path(path or self.profile.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = _build_payload(
            profile=self.profile,
            whales=whales,
            reject_summary=reject_summary,
            checked_wallet_count=checked_wallet_count,
            candidate_wallet_count=candidate_wallet_count,
            candidate_pool_summary=candidate_pool_summary or Counter(),
            generated_at=datetime.now(UTC),
        )

        with output_path.open("w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, ensure_ascii=False, indent=2)

        log_event(
            "info",
            "polymarket.whales_json.written",
            path=str(output_path),
            rows=len(whales),
        )


if __name__ == "__main__":
    tracked_whales = asyncio.run(WhaleTracker().run())
    log_event(
        "info",
        "polymarket.track_whales.returned",
        returned_wallets=len(tracked_whales),
    )
