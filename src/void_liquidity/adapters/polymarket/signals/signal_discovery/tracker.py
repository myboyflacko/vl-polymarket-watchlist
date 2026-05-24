import argparse
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
from void_liquidity.adapters.polymarket.api.client import HTTPClient
from void_liquidity.adapters.polymarket.api.endpoints.profile import (
    PolymarketRateLimitError,
)
from void_liquidity.adapters.polymarket.api.params import (
    ActivityParams,
    ClosedPositionsParams,
    CurrentPositionsParams,
    LeaderboardParams,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.config import (
    _resolve_project_path,
    load_workflow_profile,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.domain import (
    Candidate,
    CandidateEntries,
    CandidateScan,
    CandidateValidation,
    PagedRows,
    PersistContext,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.helpers import (
    _build_activity_params,
    _build_closed_positions_params,
    _build_current_positions_params,
    _build_leaderboard_params,
    _field_le,
    _parse_row_timestamp,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.metrics import (
    _aggregate_activity,
    _aggregate_closed_positions,
    _aggregate_current_positions,
    _build_candidate_pool,
    _leaderboard_metrics,
    _qualification_reasons,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.report import (
    build_report_payload,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.repository import (
    persist_whale_tracker_run,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.run_log import (
    WhaleTrackerRunLog,
)
from void_liquidity.adapters.polymarket.signals.signal_discovery.schemas import (
    WhaleTrackingProfile,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.pipeline.signal_discovery.events import (
    SIGNAL_DISCOVERY_COMPLETED,
    SIGNAL_DISCOVERY_FAILED,
    SIGNAL_DISCOVERY_STARTED,
)
from void_liquidity.logging import VoidLogger


logger = VoidLogger(__name__)


def _build_run_id(generated_at: datetime) -> str:
    return generated_at.strftime("%Y%m%dT%H%M%S%fZ")


def _append_report_run_id_to_path(path: Path, run_id: str) -> Path:
    return path.with_name(f"{path.stem}_report_{run_id}{path.suffix}")


class WhaleTracker:
    def __init__(
        self,
        profile: WhaleTrackingProfile | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.profile = profile or load_workflow_profile()
        self.event_bus = event_bus

    async def run(
        self,
        correlation_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        client = HTTPClient()
        now = datetime.now(UTC)
        run_id = _build_run_id(now)
        run_log = WhaleTrackerRunLog(profile=self.profile, run_id=run_id)

        try:
            run_log.start()
            await self._publish_event(
                event_type=SIGNAL_DISCOVERY_STARTED,
                run_id=run_id,
                correlation_id=correlation_id,
                payload={
                    "profile_version": self.profile.profile_version,
                    "target_wallet_count": self.profile.target_wallet_count,
                },
            )
            entries = await self._fetch_candidate_entries(client=client)
            scan = await self._process_candidate_batches(
                client=client,
                entries=entries,
                now=now,
            )
            self._persist_outputs(
                whales=scan.whales,
                context=PersistContext(
                    reject_summary=scan.reject_summary,
                    reject_group_summary=scan.reject_group_summary,
                    checked_wallet_count=scan.checked_wallet_count,
                    checked_group_summary=scan.checked_group_summary,
                    candidate_wallet_count=len(entries.candidates),
                    candidate_pool_summary=entries.pool_summary,
                    generated_at=now,
                    run_id=run_id,
                    started_at=run_log.started_at,
                ),
            )
            run_log.report(
                candidate_wallet_count=len(entries.candidates),
                checked_wallet_count=scan.checked_wallet_count,
                whales=scan.whales,
                reject_summary=scan.reject_summary,
                candidate_pool_summary=entries.pool_summary,
            )
            run_log.finish()
            await self._publish_event(
                event_type=SIGNAL_DISCOVERY_COMPLETED,
                run_id=run_id,
                correlation_id=correlation_id,
                payload={
                    "candidate_wallet_count": len(entries.candidates),
                    "checked_wallet_count": scan.checked_wallet_count,
                    "accepted_wallet_count": len(scan.whales),
                },
            )
            return scan.whales
        except Exception as exc:
            run_log.fail(exc)
            await self._publish_event(
                event_type=SIGNAL_DISCOVERY_FAILED,
                run_id=run_id,
                correlation_id=correlation_id,
                payload={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

        finally:
            await client.close()

    async def _publish_event(
        self,
        *,
        event_type: str,
        run_id: str,
        correlation_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        if self.event_bus is None:
            return

        await self.event_bus.publish(
            DomainEvent.create(
                event_type=event_type,
                source="polymarket.whale_tracker",
                payload={
                    "run_id": run_id,
                    **payload,
                },
                correlation_id=correlation_id,
            )
        )

    async def _fetch_candidate_entries(
        self,
        client: HTTPClient,
    ) -> CandidateEntries:
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
        typed_candidates = [
            Candidate.from_mapping(candidate) for candidate in candidates
        ]
        candidate_pool_summary = Counter(
            candidate.source for candidate in typed_candidates
        )
        return CandidateEntries(
            pnl_entries=pnl_entries,
            vol_entries=vol_entries,
            candidates=typed_candidates,
            pool_summary=candidate_pool_summary,
        )

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

            try:
                page = await get_leaderboard(client=client, params=params)
            except Exception as exc:
                logger.log_error(
                    "polymarket.leaderboard_fetch_failed",
                    exc,
                    order_by=order_by,
                    offset=offset,
                    params=params.model_dump(exclude_none=True),
                )
                raise

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
        entries: CandidateEntries,
        now: datetime,
    ) -> CandidateScan:
        whales: dict[str, dict[str, Any]] = {}
        reject_summary: Counter[str] = Counter()
        reject_group_summary: dict[str, Counter[str]] = {}
        checked_group_summary: Counter[str] = Counter()
        checked_wallet_count = 0

        for batch_start in range(
            0,
            len(entries.candidates),
            self.profile.wallet_batch_size,
        ):
            if len(whales) >= self.profile.target_wallet_count:
                break

            batch = entries.candidates[
                batch_start:batch_start + self.profile.wallet_batch_size
            ]
            results = await asyncio.gather(
                *[
                    self._validate_candidate(
                        client=client,
                        candidate=candidate,
                        pnl_entry=entries.pnl_entries.get(candidate.proxy_wallet),
                        vol_entry=entries.vol_entries.get(candidate.proxy_wallet),
                        now=now,
                    )
                    for candidate in batch
                ]
            )

            for result in results:
                candidate = result.candidate
                checked_wallet_count += 1
                checked_group_summary.update([candidate.source])

                if not result.accepted:
                    reject_summary.update(result.reject_reasons)
                    reject_group_summary.setdefault(
                        candidate.source,
                        Counter(),
                    ).update(result.reject_reasons)
                    continue

                whales[candidate.proxy_wallet] = result.whale

                if len(whales) >= self.profile.target_wallet_count:
                    break

        return CandidateScan(
            whales=whales,
            reject_summary=reject_summary,
            reject_group_summary=reject_group_summary,
            checked_wallet_count=checked_wallet_count,
            checked_group_summary=checked_group_summary,
        )

    async def _validate_candidate(
        self,
        client: HTTPClient,
        candidate: Candidate,
        pnl_entry: dict[str, Any] | None,
        vol_entry: dict[str, Any] | None,
        now: datetime,
    ) -> CandidateValidation:
        proxy_wallet = candidate.proxy_wallet
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

        current_positions = await self._fetch_all_current_positions(
            client=client,
            proxy_wallet=proxy_wallet,
        )
        exposure_metrics = _aggregate_current_positions(
            current_positions=current_positions.rows,
            is_complete=current_positions.complete,
        )

        closed_positions = await self._fetch_all_closed_positions(
            client=client,
            proxy_wallet=proxy_wallet,
            cutoff=closed_cutoff,
        )
        closed_metrics = _aggregate_closed_positions(
            closed_positions=closed_positions.rows,
            is_complete=closed_positions.complete,
            unknown_timestamp_count=closed_positions.unknown_timestamp_count,
            is_truncated=closed_positions.truncated,
        )

        activity_rows = await self._fetch_all_activity(
            client=client,
            proxy_wallet=proxy_wallet,
            start=activity_fetch_start,
            end=now,
        )
        activity_metrics = _aggregate_activity(
            activity_rows=activity_rows.rows,
            is_complete=activity_rows.complete,
            window_start=activity_window_start,
            now=now,
        )

        reasons = _qualification_reasons(
            profile=self.profile,
            exposure_metrics=exposure_metrics,
            closed_metrics=closed_metrics,
            activity_metrics=activity_metrics,
        )

        if reasons:
            return CandidateValidation(
                candidate=candidate,
                whale=None,
                reject_reasons=reasons,
            )

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
                    pnl_entry=pnl_entry,
                    vol_entry=vol_entry,
                    candidate_pool=candidate.as_metrics_payload(),
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
            },
        }
        return CandidateValidation(candidate=candidate, whale=whale, reject_reasons=[])

    async def _fetch_all_current_positions(
        self,
        client: HTTPClient,
        proxy_wallet: str,
    ) -> PagedRows:
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
            except PolymarketRateLimitError as exc:
                logger.log_error(
                    "polymarket.current_positions_fetch_failed",
                    exc,
                    proxy_wallet=proxy_wallet,
                    offset=offset,
                    is_rate_limited=True,
                    params=params.model_dump(exclude_none=True),
                )
                return PagedRows(rows=current_positions, complete=False)
            except Exception as exc:
                logger.log_error(
                    "polymarket.current_positions_fetch_failed",
                    exc,
                    proxy_wallet=proxy_wallet,
                    offset=offset,
                    is_rate_limited=False,
                    params=params.model_dump(exclude_none=True),
                )
                return PagedRows(rows=current_positions, complete=False)

            if not isinstance(page, list) or not page:
                return PagedRows(rows=current_positions, complete=True)

            current_positions.extend(row for row in page if isinstance(row, dict))

            if len(page) < params.limit:
                return PagedRows(rows=current_positions, complete=True)

            offset += params.limit

        return PagedRows(rows=current_positions, complete=True)

    async def _fetch_all_closed_positions(
        self,
        client: HTTPClient,
        proxy_wallet: str,
        cutoff: datetime,
    ) -> PagedRows:
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
            except PolymarketRateLimitError as exc:
                logger.log_error(
                    "polymarket.closed_positions_fetch_failed",
                    exc,
                    proxy_wallet=proxy_wallet,
                    offset=offset,
                    is_rate_limited=True,
                    params=params.model_dump(exclude_none=True),
                )
                return PagedRows(
                    rows=closed_positions,
                    complete=False,
                    unknown_timestamp_count=unknown_timestamp_count,
                )
            except Exception as exc:
                logger.log_error(
                    "polymarket.closed_positions_fetch_failed",
                    exc,
                    proxy_wallet=proxy_wallet,
                    offset=offset,
                    is_rate_limited=False,
                    params=params.model_dump(exclude_none=True),
                )
                return PagedRows(
                    rows=closed_positions,
                    complete=False,
                    unknown_timestamp_count=unknown_timestamp_count,
                )

            if not isinstance(page, list) or not page:
                return PagedRows(
                    rows=closed_positions,
                    complete=True,
                    unknown_timestamp_count=unknown_timestamp_count,
                )

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
                return PagedRows(
                    rows=closed_positions,
                    complete=True,
                    unknown_timestamp_count=unknown_timestamp_count,
                )

            if len(page) < params.limit:
                return PagedRows(
                    rows=closed_positions,
                    complete=True,
                    unknown_timestamp_count=unknown_timestamp_count,
                )

            if (
                len(closed_positions)
                >= self.profile.closed_positions.max_positions_per_wallet
            ):
                return PagedRows(
                    rows=closed_positions,
                    complete=True,
                    unknown_timestamp_count=unknown_timestamp_count,
                    truncated=True,
                )

            offset += params.limit

        return PagedRows(
            rows=closed_positions,
            complete=True,
            unknown_timestamp_count=unknown_timestamp_count,
        )

    async def _fetch_all_activity(
        self,
        client: HTTPClient,
        proxy_wallet: str,
        start: datetime,
        end: datetime,
    ) -> PagedRows:
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
            except PolymarketRateLimitError as exc:
                logger.log_error(
                    "polymarket.activity_fetch_failed",
                    exc,
                    proxy_wallet=proxy_wallet,
                    offset=offset,
                    is_rate_limited=True,
                    params=params.model_dump(exclude_none=True),
                )
                return PagedRows(rows=activity_rows, complete=False)
            except Exception as exc:
                logger.log_error(
                    "polymarket.activity_fetch_failed",
                    exc,
                    proxy_wallet=proxy_wallet,
                    offset=offset,
                    is_rate_limited=False,
                    params=params.model_dump(exclude_none=True),
                )
                return PagedRows(rows=activity_rows, complete=False)

            if not isinstance(page, list) or not page:
                return PagedRows(rows=activity_rows, complete=True)

            activity_rows.extend(row for row in page if isinstance(row, dict))

            if len(page) < params.limit:
                return PagedRows(rows=activity_rows, complete=True)

            offset += params.limit

        return PagedRows(rows=activity_rows, complete=False)

    def _persist_outputs(
        self,
        whales: dict[str, dict[str, Any]],
        context: PersistContext,
    ) -> None:
        generated_at = context.generated_at or datetime.now(UTC)
        run_id = context.run_id or _build_run_id(generated_at)
        started_at = context.started_at or generated_at
        finished_at = datetime.now(UTC)
        base_output_path = _resolve_project_path(
            context.path or self.profile.output_path
        )
        report_output_path = _append_report_run_id_to_path(base_output_path, run_id)
        report_output_path.parent.mkdir(parents=True, exist_ok=True)
        report_payload = build_report_payload(
            profile=self.profile,
            whales=whales,
            reject_summary=context.reject_summary,
            reject_group_summary=context.reject_group_summary,
            checked_wallet_count=context.checked_wallet_count,
            checked_group_summary=context.checked_group_summary,
            candidate_wallet_count=context.candidate_wallet_count,
            candidate_pool_summary=context.candidate_pool_summary,
            generated_at=generated_at,
            run_id=run_id,
        )

        with report_output_path.open("w", encoding="utf-8") as output_file:
            json.dump(report_payload, output_file, ensure_ascii=False, indent=2)

        persist_whale_tracker_run(
            profile=self.profile,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            generated_at=generated_at,
            candidate_wallet_count=context.candidate_wallet_count,
            checked_wallet_count=context.checked_wallet_count,
            whales=whales,
            report_path=report_output_path,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        help="Path to a whale tracking profile JSON file.",
    )
    args = parser.parse_args()
    tracker = WhaleTracker(
        profile=load_workflow_profile(args.profile) if args.profile else None,
    )
    asyncio.run(tracker.run())


if __name__ == "__main__":
    main()
