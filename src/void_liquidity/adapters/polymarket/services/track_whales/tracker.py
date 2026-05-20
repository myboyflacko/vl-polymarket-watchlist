import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

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
from void_liquidity.adapters.polymarket.services.track_whales.config import (
    _resolve_project_path,
    load_workflow_profile,
)
from void_liquidity.adapters.polymarket.services.track_whales.helpers import (
    _build_activity_params,
    _build_closed_positions_params,
    _build_current_positions_params,
    _build_leaderboard_params,
    _field_le,
    _parse_row_timestamp,
)
from void_liquidity.adapters.polymarket.services.track_whales.metrics import (
    _aggregate_activity,
    _aggregate_closed_positions,
    _aggregate_current_positions,
    _build_candidate_pool,
    _build_payload,
    _leaderboard_metrics,
    _qualification_reasons,
    _qualification_thresholds,
)
from void_liquidity.adapters.polymarket.services.track_whales.schemas import (
    WhaleTrackingProfile,
)
from void_liquidity.util.log import log_error, log_event


class WhaleTracker:
    def __init__(self, profile: WhaleTrackingProfile | None = None) -> None:
        self.profile = profile or load_workflow_profile()

    async def run(self) -> dict[str, dict[str, Any]]:
        client = HTTPClient()
        now = datetime.now(UTC)
        started_at = datetime.now(UTC)

        try:
            log_event(
                "info",
                "polymarket.track_whales.start",
                profile_version=self.profile.profile_version,
                target_wallet_count=self.profile.target_wallet_count,
                wallet_batch_size=self.profile.wallet_batch_size,
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
                candidate_wallet_count=len(candidates),
                checked_wallet_count=checked_wallet_count,
                wallet_count=len(whales),
                reject_summary=dict(sorted(reject_summary.items())),
                duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
            )
            return whales
        except Exception as exc:
            log_error(
                "polymarket.track_whales.failed",
                exc,
                profile_version=self.profile.profile_version,
                duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
            )
            raise

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
            candidate_pool_summary=dict(sorted(candidate_pool_summary.items())),
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
            page = await get_leaderboard(client=client, params=params)

            if not isinstance(page, list) or not page:
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
                    continue

                whales[proxy_wallet] = whale

                if len(whales) >= self.profile.target_wallet_count:
                    break

            log_event(
                "info",
                "polymarket.wallet_batch.done",
                batch_start=batch_start,
                batch_size=len(batch),
                checked_wallet_count=checked_wallet_count,
                qualified_wallet_count=len(whales),
                reject_summary=dict(sorted(reject_summary.items())),
            )

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

        (
            closed_positions,
            closed_complete,
            unknown_closed_timestamps,
            closed_truncated,
        ) = await self._fetch_all_closed_positions(
            client=client,
            proxy_wallet=proxy_wallet,
            cutoff=closed_cutoff,
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

