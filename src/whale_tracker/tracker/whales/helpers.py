from __future__ import annotations

import asyncio
from typing import Any, Literal

from whale_tracker.providers.polymarket.client import PolymarketDataClient
from whale_tracker.providers.polymarket.params.leaderboard.leaderboard import (
    LeaderboardParams,
)
from whale_tracker.tracker.whales.domain import (
    LeaderboardEntry,
    LeaderboardObservation,
    LeaderboardObservationMetrics,
    Whale,
    WhaleCandidate,
    WhaleIdentity,
    Whales,
)
from whale_tracker.tracker.whales.discovery import WhaleDiscoveryProfile


LeaderboardOrder = Literal["PNL", "VOL"]


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


def collect_leaderboard_whales(
    *,
    profile: WhaleDiscoveryProfile,
    candidates: list[WhaleCandidate],
    now,
) -> Whales:
    return Whales(
        whales=[
            _leaderboard_whale(candidate=candidate, generated_at=now)
            for candidate in candidates
        ],
        candidate_wallet_count=len(candidates),
        checked_wallet_count=len(candidates),
        generated_at=now,
        profile_version=profile.profile_version,
    )


async def fetch_leaderboards_from_polymarket(
    *,
    client: PolymarketDataClient,
    profile: WhaleDiscoveryProfile,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    pnl_entries, volume_entries = await asyncio.gather(
        _fetch_leaderboard(client=client, profile=profile, order_by="PNL"),
        _fetch_leaderboard(client=client, profile=profile, order_by="VOL"),
    )
    return pnl_entries, volume_entries


def select_leaderboard_candidates(
    *,
    pnl_entries: dict[str, dict[str, Any]],
    volume_entries: dict[str, dict[str, Any]],
    wallet_count: int,
) -> list[WhaleCandidate]:
    candidate_collection_complete = (
        len(pnl_entries) >= wallet_count and len(volume_entries) >= wallet_count
    )
    wallets = [*pnl_entries]

    for wallet in volume_entries:
        if wallet not in pnl_entries:
            wallets.append(wallet)

    return [
        WhaleCandidate(
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


def _parse_leaderboard_entry(row: Any) -> LeaderboardEntry | None:
    if not isinstance(row, dict):
        return None

    proxy_wallet = row.get("proxyWallet")
    if not isinstance(proxy_wallet, str):
        return None

    return LeaderboardEntry(proxy_wallet=proxy_wallet, row=row)


def _leaderboard_whale(*, candidate: WhaleCandidate, generated_at) -> Whale:
    return Whale(
        identity=_identity(candidate),
        observation=_leaderboard_observation(
            candidate=candidate,
            generated_at=generated_at,
        ),
    )


def _identity(candidate: WhaleCandidate) -> WhaleIdentity:
    row = candidate.pnl_entry or candidate.volume_entry or {}
    return WhaleIdentity(
        proxy_wallet=candidate.proxy_wallet,
        name=row.get("name"),
        pseudonym=row.get("pseudonym"),
        profile_image=row.get("profileImage"),
    )


def _leaderboard_observation_metrics(
    *,
    candidate: WhaleCandidate,
) -> LeaderboardObservationMetrics:
    pnl_entry = candidate.pnl_entry or {}
    volume_entry = candidate.volume_entry or {}

    if candidate.pnl_entry and candidate.volume_entry:
        candidate_source = "both"
    elif candidate.pnl_entry:
        candidate_source = "pnl"
    else:
        candidate_source = "volume"
    return LeaderboardObservationMetrics(
        candidate_source=candidate_source,
        pnl_rank=to_int(pnl_entry.get("rank")),
        volume_rank=to_int(volume_entry.get("rank")),
        leaderboard_pnl=to_float(pnl_entry.get("pnl")),
        leaderboard_volume=to_float(volume_entry.get("vol")),
    )


def _leaderboard_observation(
    *,
    candidate: WhaleCandidate,
    generated_at,
) -> LeaderboardObservation:
    return LeaderboardObservation(
        proxy_wallet=candidate.proxy_wallet,
        metrics=_leaderboard_observation_metrics(candidate=candidate),
        generated_at=generated_at,
    )
