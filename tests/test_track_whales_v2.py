import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from void_liquidity.adapters.polymarket.params import ActivityParams
from void_liquidity.adapters.polymarket.services.track_whales import (
    WhaleTracker,
    WhaleTrackingProfile,
    load_workflow_profile,
)
from void_liquidity.adapters.polymarket.services.track_whales.config import (
    PROJECT_ROOT,
    _resolve_project_path,
)
from void_liquidity.adapters.polymarket.services.track_whales.metrics import (
    _aggregate_closed_positions,
    _build_candidate_pool,
    _qualification_reasons,
)
from void_liquidity.adapters.polymarket.services.track_whales.schemas import (
    ActivityConfig,
    CandidatePoolConfig,
    ClosedPositionsConfig,
    CurrentPositionsConfig,
    WhaleFilterConfig,
)
from void_liquidity.adapters.polymarket.services.track_whales import (
    tracker as tracker_module,
)


WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class FakeHTTPClient:
    async def close(self) -> None:
        return None


class FrozenDateTime(datetime):
    frozen_now: datetime

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        if tz is None:
            return cls.frozen_now.replace(tzinfo=None)

        return cls.frozen_now.astimezone(tz)


def _profile(output_path: Path) -> WhaleTrackingProfile:
    return WhaleTrackingProfile(
        target_wallet_count=10,
        wallet_batch_size=2,
        output_path=str(output_path),
        candidate_pool=CandidatePoolConfig(top_n=2, leaderboard_limit=2),
        current_positions=CurrentPositionsConfig(limit=10),
        closed_positions=ClosedPositionsConfig(
            window_days=30,
            limit=50,
            max_positions_per_wallet=100,
        ),
        activity=ActivityConfig(
            trade_count_window_days=30,
            min_trade_count=10,
            last_activity_max_age_days=7,
            limit=500,
        ),
        filters=WhaleFilterConfig(
            min_current_position_value=10_000,
            min_closed_trade_count=50,
            min_win_rate=0.70,
            min_closed_positions_pnl=0,
        ),
    )


def _closed_positions(now: datetime) -> list[dict[str, Any]]:
    rows = []

    for index in range(50):
        rows.append(
            {
                "timestamp": int((now - timedelta(days=1)).timestamp()),
                "realizedPnl": 100 if index < 40 else -10,
            }
        )

    return rows


def _activity(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": int((now - timedelta(days=1)).timestamp()),
            "type": "TRADE",
            "usdcSize": 100,
        }
        for _ in range(10)
    ]


def test_track_whales_filters_and_writes_v2_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VOID_LIQUIDITY_LOG_DIR", str(tmp_path / "logs"))
    now = datetime(2026, 5, 20, tzinfo=UTC)
    FrozenDateTime.frozen_now = now
    output_path = tmp_path / "whales.json"
    profile = _profile(output_path)

    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        if params.orderBy == "PNL":
            return [
                {
                    "rank": "1",
                    "proxyWallet": WALLET_ONE,
                    "userName": "winner",
                    "pnl": 10_000,
                    "vol": 50_000,
                },
                {
                    "rank": "2",
                    "proxyWallet": WALLET_TWO,
                    "userName": "small",
                    "pnl": 9_000,
                    "vol": 40_000,
                },
            ]

        return [
            {
                "rank": "1",
                "proxyWallet": WALLET_ONE,
                "userName": "winner",
                "pnl": 10_000,
                "vol": 50_000,
            },
            {
                "rank": "2",
                "proxyWallet": WALLET_TWO,
                "userName": "small",
                "pnl": 9_000,
                "vol": 40_000,
            },
        ]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        if params.user == WALLET_ONE:
            return [{"currentValue": 15_000, "initialValue": 10_000}]

        return [{"currentValue": 1_000, "initialValue": 1_000}]

    async def fake_get_closed_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        if params.offset:
            return []

        return _closed_positions(now)

    async def fake_get_activity(
        client: Any,
        params: ActivityParams,
    ) -> list[dict[str, Any]]:
        assert params.start is not None
        assert params.end is not None
        return _activity(now)

    monkeypatch.setattr(tracker_module, "HTTPClient", FakeHTTPClient)
    monkeypatch.setattr(tracker_module, "get_leaderboard", fake_get_leaderboard)
    monkeypatch.setattr(
        tracker_module,
        "get_current_positions",
        fake_get_current_positions,
    )
    monkeypatch.setattr(
        tracker_module,
        "get_closed_positions",
        fake_get_closed_positions,
    )
    monkeypatch.setattr(tracker_module, "get_activity", fake_get_activity)
    monkeypatch.setattr(tracker_module, "datetime", FrozenDateTime)

    whales = asyncio.run(WhaleTracker(profile=profile).run())

    assert list(whales) == [WALLET_ONE]
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["mode"] == "fresh_discovery"
    assert payload["metadata"]["wallet_count"] == 1
    assert payload["metadata"]["reject_summary"] == {
        "current_position_value_below_min": 1,
    }
    assert payload["whales"][WALLET_ONE]["metadata"]["user_name"] == "winner"
    assert "leaderboard" in payload["whales"][WALLET_ONE]["metrics"]
    assert "exposure" in payload["whales"][WALLET_ONE]["metrics"]
    assert "closed_positions" in payload["whales"][WALLET_ONE]["metrics"]
    assert "activity" in payload["whales"][WALLET_ONE]["metrics"]
    assert payload["whales"][WALLET_ONE]["metrics"]["qualification"]["passed"] is True


def test_load_default_workflow_profile() -> None:
    profile = load_workflow_profile()

    assert profile.profile_version == "whale_tracking_v2"
    assert profile.candidate_pool.top_n == 250
    assert profile.activity.trade_count_window_days == 30
    assert profile.activity.last_activity_max_age_days == 7


def test_resolve_project_path_uses_repo_root_for_relative_paths() -> None:
    resolved_path = _resolve_project_path(
        "src/void_liquidity/adapters/polymarket/services/data/polymarket_whales.json"
    )

    assert resolved_path == (
        PROJECT_ROOT
        / "src/void_liquidity/adapters/polymarket/services/data/polymarket_whales.json"
    )


def test_fetch_all_activity_marks_max_offset_exhaustion_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VOID_LIQUIDITY_LOG_DIR", str(tmp_path / "logs"))
    output_path = tmp_path / "whales.json"
    profile = _profile(output_path)
    page = [
        {
            "timestamp": 1_779_303_814,
            "type": "TRADE",
            "usdcSize": 100,
        }
        for _ in range(profile.activity.limit)
    ]

    async def fake_get_activity(
        client: Any,
        params: ActivityParams,
    ) -> list[dict[str, Any]]:
        return page

    monkeypatch.setattr(tracker_module, "get_activity", fake_get_activity)

    rows, is_complete = asyncio.run(
        WhaleTracker(profile=profile)._fetch_all_activity(
            client=FakeHTTPClient(),
            proxy_wallet=WALLET_ONE,
            start=datetime(2026, 5, 1, tzinfo=UTC),
            end=datetime(2026, 5, 20, tzinfo=UTC),
        )
    )

    assert len(rows) == 3500
    assert is_complete is False


def test_incomplete_activity_is_not_a_reject_reason(tmp_path: Path) -> None:
    profile = _profile(tmp_path / "whales.json")

    reasons = _qualification_reasons(
        profile=profile,
        exposure_metrics={
            "current_positions_complete": True,
            "current_position_value": 10_000,
        },
        closed_metrics={
            "closed_positions_complete": True,
            "closed_trade_count": 50,
            "win_rate": 0.70,
            "closed_positions_pnl": 1,
        },
        activity_metrics={
            "activity_complete": False,
            "trade_count_window": 3500,
            "last_activity_age_days": 0.1,
        },
    )

    assert reasons == []


def test_whale_tracker_instances_keep_independent_profiles(tmp_path: Path) -> None:
    first_profile = _profile(tmp_path / "first.json")
    second_profile = _profile(tmp_path / "second.json")
    second_profile.target_wallet_count = 3

    first_tracker = WhaleTracker(profile=first_profile)
    second_tracker = WhaleTracker(profile=second_profile)

    assert first_tracker.profile.output_path == str(tmp_path / "first.json")
    assert first_tracker.profile.target_wallet_count == 10
    assert second_tracker.profile.output_path == str(tmp_path / "second.json")
    assert second_tracker.profile.target_wallet_count == 3


def test_build_candidate_pool_splits_core_specialists_and_profitable_volume() -> None:
    pnl_entries = {
        WALLET_ONE: {"proxyWallet": WALLET_ONE, "pnl": 100},
        WALLET_TWO: {"proxyWallet": WALLET_TWO, "pnl": 80},
    }
    volume_only = "0xcccccccccccccccccccccccccccccccccccccccc"
    losing_volume = "0xdddddddddddddddddddddddddddddddddddddddd"
    vol_entries = {
        WALLET_ONE: {"proxyWallet": WALLET_ONE, "pnl": 100},
        volume_only: {"proxyWallet": volume_only, "pnl": 10},
        losing_volume: {"proxyWallet": losing_volume, "pnl": -1},
    }

    candidates = _build_candidate_pool(
        pnl_entries=pnl_entries,
        vol_entries=vol_entries,
    )

    assert candidates == [
        {
            "proxy_wallet": WALLET_ONE,
            "source": "core",
            "matched_pools": ["core", "pnl_top", "volume_top"],
        },
        {
            "proxy_wallet": WALLET_TWO,
            "source": "pnl_specialist",
            "matched_pools": ["pnl_top"],
        },
        {
            "proxy_wallet": volume_only,
            "source": "volume_profitable",
            "matched_pools": ["volume_top"],
        },
    ]


def test_closed_position_metrics_include_risk_return_ratios() -> None:
    metrics = _aggregate_closed_positions(
        closed_positions=[
            {"realizedPnl": 30, "initialValue": 100},
            {"realizedPnl": 10, "initialValue": 100},
            {"realizedPnl": -20, "initialValue": 100},
        ],
        is_complete=True,
        unknown_timestamp_count=0,
    )

    assert metrics["closed_positions_volume"] == 300
    assert metrics["roi"] == pytest.approx(20 / 300)
    assert metrics["gross_profit"] == 40
    assert metrics["gross_loss"] == 20
    assert metrics["profit_factor"] == 2
    assert metrics["avg_win"] == 20
    assert metrics["avg_loss"] == 20
    assert metrics["largest_loss"] == 20


def test_closed_position_metrics_mark_truncated_samples() -> None:
    metrics = _aggregate_closed_positions(
        closed_positions=[{"realizedPnl": 1, "initialValue": 10}],
        is_complete=True,
        unknown_timestamp_count=0,
        is_truncated=True,
    )

    assert metrics["closed_positions_complete"] is True
    assert metrics["closed_positions_truncated"] is True
