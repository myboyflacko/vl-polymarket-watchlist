from datetime import UTC, datetime

from whale_tracker.tracker.whales.domain import (
    LeaderboardObservation,
    Whale,
    WhaleIdentity,
    Whales,
)
from whale_tracker.tracker.whales.filter import TrackedWhaleFilterProfile


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_tracked_whale_filter_requires_three_recent_runs() -> None:
    result = TrackedWhaleFilterProfile(required_consecutive_runs=3).run(
        run_id="run-3",
        whales=_whales(["wallet-1"]),
        recent_run_wallets=[["wallet-1"], ["wallet-1"]],
    )

    assert result.wallet_count == 0


def test_tracked_whale_filter_tracks_wallets_seen_in_all_recent_runs() -> None:
    result = TrackedWhaleFilterProfile(required_consecutive_runs=3).run(
        run_id="run-3",
        whales=_whales(["wallet-1", "wallet-2"]),
        recent_run_wallets=[
            ["wallet-1", "wallet-2"],
            ["wallet-1"],
            ["wallet-1", "wallet-2"],
        ],
    )

    assert result.proxy_wallets() == ["wallet-1"]


def test_tracked_whale_filter_requires_wallet_in_current_run() -> None:
    result = TrackedWhaleFilterProfile(required_consecutive_runs=3).run(
        run_id="run-3",
        whales=_whales(["wallet-1"]),
        recent_run_wallets=[
            ["wallet-1", "wallet-2"],
            ["wallet-1", "wallet-2"],
            ["wallet-1", "wallet-2"],
        ],
    )

    assert result.proxy_wallets() == ["wallet-1"]


def _whales(wallets: list[str]) -> Whales:
    return Whales(
        whales=[
            Whale(
                identity=WhaleIdentity(proxy_wallet=wallet),
                observation=LeaderboardObservation(
                    proxy_wallet=wallet,
                    candidate_source="both",
                    generated_at=NOW,
                ),
            )
            for wallet in wallets
        ],
        candidate_wallet_count=len(wallets),
        checked_wallet_count=len(wallets),
        generated_at=NOW,
        profile_version="test",
    )
