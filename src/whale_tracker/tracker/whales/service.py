from __future__ import annotations

from datetime import UTC, datetime

from whale_tracker.core.time import ensure_utc
from whale_tracker.providers.polymarket.client import get_polymarket_data_client
from whale_tracker.tracker.whales.domain import (
    WhaleRunResult,
    WhaleTrackingResult,
    Whales,
)
from whale_tracker.tracker.whales.discovery import WhaleDiscoveryProfile
from whale_tracker.tracker.whales.filter import DefaultWhaleFilterProfile
from whale_tracker.tracker.whales.helpers import (
    collect_leaderboard_whales,
    fetch_leaderboards_from_polymarket,
    select_leaderboard_candidates,
)
from whale_tracker.tracker.whales.repository import (
    list_discovered_whales,
    list_latest_discovered_whales,
    list_latest_selected_whale_wallets,
    list_selected_whale_wallets,
    list_selected_whales,
    persist_whale_run,
    persist_tracked_whales,
)
from whale_tracker.tracker.whales.scoring import (
    WhaleScoringProfile,
)


class WhaleTrackerService:
    def __init__(
        self,
        discovery_profile: WhaleDiscoveryProfile | None = None,
        *,
        filter_profile: DefaultWhaleFilterProfile | None = None,
        scoring_profile: WhaleScoringProfile | None = None,
    ) -> None:
        self.discovery_profile = discovery_profile or WhaleDiscoveryProfile()
        self.filter_profile = filter_profile or DefaultWhaleFilterProfile()
        self.scoring_profile = scoring_profile

    def register_filter(self, profile: DefaultWhaleFilterProfile) -> None:
        self.filter_profile = profile

    def register_scoring(self, profile: WhaleScoringProfile | None) -> None:
        self.scoring_profile = profile

    async def run(self, *, now: datetime | None = None) -> WhaleRunResult:
        started_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(started_at, suffix="whales")

        whales = await self.discover(now=started_at)
        filtered_whales = self.filter_profile.run(whales)
        scored_whales = (
            self.scoring_profile.run(filtered_whales)
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
        tracked_whales = persist_tracked_whales(run_id=run_id)

        return WhaleTrackingResult(
            run_id=run_id,
            whales=whales,
            filtered_whales=filtered_whales,
            scored_whales=scored_whales,
            tracked_whales=tracked_whales,
            collection_errors=whales.collection_errors,
        )

    async def discover(self, *, now: datetime | None = None) -> Whales:
        generated_at = ensure_utc(now or datetime.now(UTC))
        client = get_polymarket_data_client()
        pnl_entries, volume_entries = await fetch_leaderboards_from_polymarket(
            client=client,
            profile=self.discovery_profile,
        )
        candidates = select_leaderboard_candidates(
            pnl_entries=pnl_entries,
            volume_entries=volume_entries,
            wallet_count=self.discovery_profile.wallet_count,
        )
        return collect_leaderboard_whales(
            profile=self.discovery_profile,
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
