from __future__ import annotations

import logging
from datetime import UTC, datetime

from whale_tracker.providers.polymarket.client import get_polymarket_data_client
from whale_tracker.tracker.whales.domain import (
    WhaleRunResult,
    WhaleTrackingResult,
    Whales,
)
from whale_tracker.tracker.whales.filter import (
    WhaleFilterProfile,
    filter_whales,
)
from whale_tracker.tracker.whales.helpers import (
    collect_whales_from_polymarket,
    fetch_leaderboards_from_polymarket,
    select_leaderboard_candidates,
)
from whale_tracker.tracker.whales.profiles import WhaleDiscoveryProfile
from whale_tracker.tracker.whales.repository import (
    list_discovered_whales,
    list_latest_discovered_whales,
    list_latest_selected_whale_wallets,
    list_selected_whale_wallets,
    list_selected_whales,
    persist_whale_run,
)
from whale_tracker.tracker.whales.scoring import WhaleScoringProfile, score_whales


logger = logging.getLogger(__name__)


class WhaleTrackerService:
    def __init__(
        self,
        profile: WhaleDiscoveryProfile | None = None,
        *,
        filter_profile: WhaleFilterProfile | None = None,
        scoring_profile: WhaleScoringProfile | None = None,
    ) -> None:
        self.profile = profile or WhaleDiscoveryProfile()
        self.filter_profile = filter_profile or self.profile.filter
        self.scoring_profile = scoring_profile or self.profile.scoring or WhaleScoringProfile()

    def register_filter(self, profile: WhaleFilterProfile) -> None:
        self.filter_profile = profile

    def register_scoring(self, profile: WhaleScoringProfile | None) -> None:
        self.scoring_profile = profile

    async def run(self, *, now: datetime | None = None) -> WhaleRunResult:
        started_at = now or datetime.now(UTC)
        run_id = _build_run_id(started_at, suffix="whales")

        try:
            whales = await self.discover(now=started_at)
            filtered_whales = filter_whales(
                whales=whales,
                profile=self.filter_profile,
            )
            scored_whales = (
                score_whales(
                    filtered_whales=filtered_whales,
                    profile=self.scoring_profile,
                )
                if self.scoring_profile is not None
                else None
            )
            persist_whale_run(
                run_id=run_id,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                whales=whales,
                filtered_whales=filtered_whales,
                scored_whales=scored_whales,
            )
        except Exception:
            logger.exception("Whale tracking run failed", extra={"run_id": run_id})
            raise

        return WhaleTrackingResult(
            run_id=run_id,
            whales=whales,
            filtered_whales=filtered_whales,
            scored_whales=scored_whales,
            collection_errors=whales.collection_errors,
        )

    async def discover(self, *, now: datetime | None = None) -> Whales:
        generated_at = now or datetime.now(UTC)
        client = get_polymarket_data_client()
        pnl_entries, volume_entries = await fetch_leaderboards_from_polymarket(
            client=client,
            profile=self.profile,
        )
        candidates = select_leaderboard_candidates(
            pnl_entries=pnl_entries,
            volume_entries=volume_entries,
            wallet_count=self.profile.wallet_count,
        )
        return await collect_whales_from_polymarket(
            client=client,
            profile=self.profile,
            candidates=candidates,
            now=generated_at,
        )

    def list_prefiltered(self, *, run_id: str | None = None) -> Whales:
        if run_id is None:
            return list_latest_discovered_whales()

        return list_discovered_whales(run_id)

    def list_selected(self, *, run_id: str | None = None) -> Whales:
        if run_id is None:
            wallets = set(list_latest_selected_whale_wallets())
            whales = list_latest_discovered_whales()
            return whales.model_copy(
                update={
                    "whales": [
                        whale for whale in whales.whales if whale.proxy_wallet in wallets
                    ],
                }
            )

        return list_selected_whales(run_id)

    def list_selected_wallets(self, *, run_id: str | None = None) -> list[str]:
        if run_id is None:
            return list_latest_selected_whale_wallets()

        return list_selected_whale_wallets(run_id)


def _build_run_id(generated_at: datetime, *, suffix: str) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-{suffix}"
