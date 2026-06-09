from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from whale_tracker.tracker.whales.domain import (
    TrackedWhale,
    TrackedWhales,
    Whale,
    Whales,
)


class TrackedWhaleFilterProfile(BaseModel):
    name: str = "leaderboard_streak_3_v1"
    required_consecutive_runs: int = Field(default=3, ge=1)

    def run(
        self,
        *,
        run_id: str,
        whales: Whales,
        recent_run_wallets: list[list[str]],
    ) -> TrackedWhales:
        if len(recent_run_wallets) < self.required_consecutive_runs:
            return _tracked_whales(
                run_id=run_id,
                whales=[],
                source=whales,
                filter_profile=self.name,
                consecutive_runs=self.required_consecutive_runs,
            )

        wallet_counts = Counter(
            wallet
            for run_wallets in recent_run_wallets[: self.required_consecutive_runs]
            for wallet in set(run_wallets)
        )
        tracked = [
            whale
            for whale in whales.whales
            if wallet_counts[whale.proxy_wallet] == self.required_consecutive_runs
        ]
        return _tracked_whales(
            run_id=run_id,
            whales=tracked,
            source=whales,
            filter_profile=self.name,
            consecutive_runs=self.required_consecutive_runs,
        )


def _tracked_whales(
    *,
    run_id: str,
    whales: list[Whale],
    source: Whales,
    filter_profile: str,
    consecutive_runs: int,
) -> TrackedWhales:
    return TrackedWhales(
        whales=[
            TrackedWhale(
                proxy_wallet=whale.proxy_wallet,
                run_id=run_id,
                generated_at=source.generated_at,
                filter_profile=filter_profile,
                consecutive_runs=consecutive_runs,
                candidate_source=whale.observation.candidate_source,
                pnl_rank=whale.observation.pnl_rank,
                volume_rank=whale.observation.volume_rank,
                leaderboard_pnl=whale.observation.leaderboard_pnl,
                leaderboard_volume=whale.observation.leaderboard_volume,
                identity=whale.identity,
            )
            for whale in whales
        ],
        run_id=run_id,
        generated_at=source.generated_at,
        filter_profile=filter_profile,
    )
