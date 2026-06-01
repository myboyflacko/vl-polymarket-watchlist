from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from void_liquidity.adapters.polymarket.api.client import (
    PolymarketDataClient,
    get_polymarket_data_client,
)
from void_liquidity.adapters.polymarket.api.params.leaderboard.leaderboard import (
    LeaderboardParams,
)
from void_liquidity.adapters.polymarket.api.params.profile.current_positions import (
    CurrentPositionsParams,
)
from void_liquidity.adapters.polymarket.api.params.profile.trades import TradesParams
from void_liquidity.adapters.polymarket.markets.whales.discovery.domain import (
    LeaderboardMetrics,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    WalletCollectionError,
    Whales,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.helpers import (
    row_timestamp,
    to_float,
    to_int,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.metrics import (
    aggregate_current_positions,
    aggregate_trades,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
    persist_whale_discovery_run,
)


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


class WhaleDiscoveryService:
    def __init__(self, profile: WhaleDiscoveryProfile | None = None) -> None:
        self.profile = profile or WhaleDiscoveryProfile()

    async def run(self, *, now: datetime | None = None) -> Whales:
        generated_at = now or datetime.now(UTC)
        client = get_polymarket_data_client()

        candidates = await self._fetch_candidates(client=client)
        whales = await self._collect_whales(
            client=client,
            candidates=candidates,
            now=generated_at,
        )
        return Whales(
            whales=whales,
            candidate_wallet_count=len(candidates),
            checked_wallet_count=len(candidates),
            generated_at=generated_at,
            profile_version=self.profile.profile_version,
            collection_errors=self._collection_errors,
        )

    def persist(
        self,
        *,
        whales: Whales,
        run_id: str,
        started_at: datetime,
        finished_at: datetime | None = None,
    ) -> None:
        persist_whale_discovery_run(
            profile=self.profile,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at or datetime.now(UTC),
            generated_at=whales.generated_at,
            whales=whales,
        )

    async def _fetch_candidates(self, client: PolymarketDataClient) -> list[_Candidate]:
        pnl_entries, volume_entries = await asyncio.gather(
            self._fetch_leaderboard(client=client, order_by="PNL"),
            self._fetch_leaderboard(client=client, order_by="VOL"),
        )
        candidate_collection_complete = (
            len(pnl_entries) >= self.profile.wallet_count
            and len(volume_entries) >= self.profile.wallet_count
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
        self,
        *,
        client: PolymarketDataClient,
        order_by: LeaderboardOrder,
    ) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        offset = 0
        max_offset = 1000

        while len(entries) < self.profile.wallet_count and offset <= max_offset:
            params = LeaderboardParams(
                category=self.profile.leaderboard_category,
                timePeriod=self.profile.leaderboard_time_period,
                orderBy=order_by,
                limit=self.profile.leaderboard_limit,
                offset=offset,
            )
            page = await client.get_leaderboard(params)

            if not isinstance(page, list) or not page:
                break

            for row in page:
                entry = self._parse_leaderboard_entry(row)
                if entry is None:
                    continue

                entries.setdefault(entry.proxy_wallet, entry.row)

                if len(entries) >= self.profile.wallet_count:
                    break

            if len(page) < params.limit:
                break

            offset += params.limit

        return entries

    def _parse_leaderboard_entry(self, row: Any) -> _LeaderboardEntry | None:
        if not isinstance(row, dict):
            return None

        proxy_wallet = row.get("proxyWallet")
        if not isinstance(proxy_wallet, str):
            return None

        return _LeaderboardEntry(proxy_wallet=proxy_wallet, row=row)

    async def _collect_whales(
        self,
        *,
        client: PolymarketDataClient,
        candidates: list[_Candidate],
        now: datetime,
    ) -> list[Whale]:
        whales: list[Whale] = []
        self._collection_errors: list[WalletCollectionError] = []

        for batch_start in range(0, len(candidates), self.profile.wallet_batch_size):
            batch = candidates[
                batch_start : batch_start + self.profile.wallet_batch_size
            ]
            results = await asyncio.gather(
                *[
                    self._collect_whale_safely(
                        client=client,
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
                    self._collection_errors.append(result.error)

        return whales

    async def _collect_whale_safely(
        self,
        *,
        client: PolymarketDataClient,
        candidate: _Candidate,
        now: datetime,
    ) -> _WalletCollectionResult:
        try:
            return _WalletCollectionResult(
                whale=await self._collect_whale(
                    client=client,
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
        self,
        *,
        client: PolymarketDataClient,
        candidate: _Candidate,
        now: datetime,
    ) -> Whale:
        try:
            trade_rows = await self._fetch_window_trades(
                client=client,
                proxy_wallet=candidate.proxy_wallet,
                now=now,
            )
        except Exception as exc:
            raise _WalletStageError("trades") from exc
        trade_metrics, market_metrics, quality, condition_ids = aggregate_trades(
            trades=trade_rows.rows,
            now=now,
            trade_window_days=self.profile.trade_window_days,
            recent_window_days=self.profile.recent_window_days,
            trades_complete=trade_rows.complete,
            trades_sort_order=trade_rows.sort_order,
            invalid_trade_row_count=trade_rows.invalid_row_count,
        )
        try:
            current_positions = await self._fetch_current_positions(
                client=client,
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
                "candidate_collection_complete": (
                    candidate.candidate_collection_complete
                ),
            }
        )

        return Whale(
            identity=self._identity(candidate=candidate, trades=trade_rows.rows),
            condition_ids_30d=condition_ids,
            metrics=WhaleMetrics(
                leaderboard=self._leaderboard_metrics(candidate),
                trades=trade_metrics,
                markets=market_metrics,
                exposure=exposure_metrics,
                collection_quality=quality,
            ),
        )

    def _identity(
        self,
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

    def _leaderboard_metrics(self, candidate: _Candidate) -> LeaderboardMetrics:
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
        self,
        *,
        client: PolymarketDataClient,
        proxy_wallet: str,
        now: datetime,
    ) -> _TradePageRows:
        rows: list[dict[str, Any]] = []
        offset = 0
        page_count = 0
        sort_order: Literal["desc", "unknown"] = "desc"
        invalid_row_count = 0
        window_start = now - timedelta(days=self.profile.trade_window_days)

        while offset <= 10_000 and page_count < self.profile.max_trade_pages_per_wallet:
            params = TradesParams(
                user=proxy_wallet,
                limit=self.profile.trade_limit,
                offset=offset,
                takerOnly=self.profile.taker_only,
            )
            page = await client.get_trades(params)

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

            if not _is_descending(page_timestamps):
                sort_order = "unknown"

            rows.extend(page_rows)

            if (
                sort_order == "desc"
                and page_timestamps
                and max(page_timestamps) < window_start
            ):
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
        self,
        *,
        client: PolymarketDataClient,
        proxy_wallet: str,
        condition_ids: list[str],
    ) -> _CurrentPositionRows:
        if not condition_ids:
            return _CurrentPositionRows(rows=[], complete=True)

        rows: list[dict[str, Any]] = []
        complete = True

        for condition_id_chunk in _chunks(
            condition_ids,
            self.profile.current_positions_market_chunk_size,
        ):
            offset = 0

            while offset <= 10_000:
                params = CurrentPositionsParams(
                    user=proxy_wallet,
                    market=condition_id_chunk,
                    limit=self.profile.current_positions_limit,
                    offset=offset,
                    sortBy="CURRENT",
                    sortDirection="DESC",
                )
                page = await client.get_current_positions(params)

                if not isinstance(page, list) or not page:
                    break

                rows.extend(row for row in page if isinstance(row, dict))

                if len(page) < params.limit:
                    break

                offset += params.limit
            else:
                complete = False

        return _CurrentPositionRows(rows=rows, complete=complete)


def _is_descending(values: list[datetime]) -> bool:
    return all(left >= right for left, right in zip(values, values[1:], strict=False))


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


class _WalletStageError(RuntimeError):
    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage
