import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from void_liquidity.adapters.polymarket.api.params import ActivityParams
from void_liquidity.adapters.polymarket.discovery.whales import (
    WhaleTracker,
    WhaleTrackingProfile,
    load_workflow_profile,
)
from void_liquidity.adapters.polymarket.discovery.whales.config import (
    PROJECT_ROOT,
    QUALITY_PROFILE_PATH,
    _resolve_project_path,
)
from void_liquidity.adapters.polymarket.discovery.whales.domain import (
    Candidate,
    CandidateEntries,
    CandidateScan,
)
from void_liquidity.adapters.polymarket.discovery.whales.models import (
    TrackedWhale,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.discovery.whales.metrics import (
    _aggregate_closed_positions,
    _build_candidate_pool,
    _qualification_reasons,
)
from void_liquidity.adapters.polymarket.discovery.whales.report import (
    build_report_payload,
)
from void_liquidity.adapters.polymarket.discovery.whales.schemas import (
    ActivityConfig,
    CandidatePoolConfig,
    ClosedPositionsConfig,
    CurrentPositionsConfig,
    WhaleFilterConfig,
)
from void_liquidity.adapters.polymarket.discovery.whales import (
    tracker as tracker_module,
)
from void_liquidity.data import Base, create_database_engine, database_session
from void_liquidity.settings import DEFAULT_SQLITE_PATH, get_settings


WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
WALLET_THREE = "0xcccccccccccccccccccccccccccccccccccccccc"
WALLET_FOUR = "0xdddddddddddddddddddddddddddddddddddddddd"


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
            min_closed_positions_pnl=0,
            min_roi=0,
            min_profit_factor=1.5,
            min_activity_volume=10_000,
            max_largest_win_share=0.60,
        ),
    )


def _create_test_schema(database_path: Path) -> None:
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)


def _closed_positions(now: datetime) -> list[dict[str, Any]]:
    rows = []

    for index in range(50):
        rows.append(
            {
                "timestamp": int((now - timedelta(days=1)).timestamp()),
                "realizedPnl": 100 if index < 40 else -10,
                "totalBought": 1_000,
                "avgPrice": 0.5,
            }
        )

    return rows


def _activity(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": int((now - timedelta(days=1)).timestamp()),
            "type": "TRADE",
            "usdcSize": 1_000,
        }
        for _ in range(10)
    ]


def _tracked_whale_payload(
    proxy_wallet: str,
    *,
    current_position_value: float,
) -> dict[str, Any]:
    return {
        "metadata": {
            "proxy_wallet": proxy_wallet,
            "user_name": proxy_wallet,
            "x_username": "",
            "profile_image": None,
            "verified_badge": False,
        },
        "metrics": {
            "leaderboard": {
                "candidate_pool_source": "core",
                "matched_pools": ["core", "pnl_top", "volume_top"],
                "pnl_rank": "1",
                "vol_rank": "1",
                "leaderboard_pnl": 100,
                "leaderboard_volume": 1_000,
            },
            "exposure": {
                "open_position_count": 1,
                "current_position_value": current_position_value,
                "largest_position_value": current_position_value,
                "position_concentration": 1,
                "current_positions_complete": True,
            },
            "closed_positions": {
                "closed_trade_count": 50,
                "closed_positions_pnl": 100,
                "closed_positions_cost_basis": 500,
                "roi": 0.2,
                "roi_available": True,
                "profit_factor": 2,
                "gross_profit": 200,
                "gross_loss": 100,
                "avg_win": 20,
                "avg_loss": 10,
                "largest_win": 50,
                "largest_win_share": 0.25,
                "largest_loss": 30,
                "closed_positions_complete": True,
                "closed_positions_truncated": False,
            },
            "activity": {
                "trade_count_window": 10,
                "trade_count_7d": 5,
                "activity_volume_window": 10_000,
                "activity_volume_7d": 5_000,
                "last_activity_at": datetime(2026, 5, 20, tzinfo=UTC).isoformat(),
                "last_activity_age_days": 0,
                "activity_complete": True,
                "activity_capped": False,
            },
        },
    }


def test_track_whales_filters_and_writes_v2_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VOID_LIQUIDITY_LOG_DIR", str(tmp_path / "logs"))
    now = datetime(2026, 5, 20, tzinfo=UTC)
    FrozenDateTime.frozen_now = now
    output_path = tmp_path / "whales.json"
    database_path = output_path.with_suffix(".sqlite3")
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    profile = _profile(output_path)
    _create_test_schema(database_path)

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

    result = asyncio.run(
        WhaleTracker(profile=profile).run(
            run_id="test-run",
            started_at=now,
        )
    )

    assert list(result.whales) == [WALLET_ONE]
    assert result.candidate_wallet_count == 2
    assert result.checked_wallet_count == 2
    assert result.accepted_wallet_count == 1
    assert result.request_errors == []
    assert [
        path
        for path in tmp_path.glob("whales_*.json")
        if "_report_" not in path.name
    ] == []
    report_files = list(tmp_path.glob("whales_report_*.json"))
    assert len(report_files) == 1

    report_payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    run_id = report_payload["metadata"]["run_id"]
    assert run_id == "test-run"
    assert report_payload["metadata"]["mode"] == "fresh_discovery"
    assert report_payload["metadata"]["wallet_count"] == 1
    assert report_payload["candidate_funnel"]["reject_summary"] == {
        "current_position_value_below_min": 1,
    }
    assert report_payload["candidate_funnel"]["by_group"]["core"]["checked_count"] == 2
    assert report_payload["candidate_funnel"]["by_group"]["core"]["accepted_count"] == 1
    assert report_payload["accepted_metrics"]["overall"][
        "closed_positions.roi"
    ]["median"] == pytest.approx(3_900 / 25_000)

    engine = create_database_engine(database_path)
    with Session(engine) as session:
        run_row = session.execute(
            select(WhaleTrackerRun).where(WhaleTrackerRun.run_id == run_id)
        ).scalar_one()
        whale_row = session.execute(
            select(TrackedWhale).where(TrackedWhale.run_id == run_id)
        ).scalar_one()

    assert run_row.profile_version == profile.profile_version
    assert run_row.candidate_wallet_count == 2
    assert run_row.checked_wallet_count == 2
    assert run_row.accepted_wallet_count == 1
    assert run_row.report_path == str(report_files[0])
    assert whale_row.proxy_wallet == WALLET_ONE
    assert whale_row.user_name == "winner"
    assert whale_row.candidate_pool_source == "core"
    whale_metrics = {
        "leaderboard": whale_row.leaderboard,
        "exposure": whale_row.exposure,
        "closed_positions": whale_row.closed_positions,
        "activity": whale_row.activity,
    }
    assert "qualification" not in whale_metrics
    assert "win_rate" not in whale_metrics["closed_positions"]
    assert "initial_position_value" not in whale_metrics["exposure"]
    assert "candidate_pool_match" not in whale_metrics["leaderboard"]
    assert whale_metrics["closed_positions"]["largest_win"] == 100
    assert whale_metrics["closed_positions"]["largest_win_share"] == pytest.approx(
        100 / 4_000,
    )
    assert (
        report_payload["profile"]["qualification_thresholds"]["max_largest_win_share"]
        == 0.60
    )
    assert report_payload["metric_quality_summary"] == {
        "activity_capped_count": 0,
        "closed_positions_truncated_count": 0,
        "roi_unavailable_count": 0,
    }


def test_track_whales_ranks_before_writing_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VOID_LIQUIDITY_LOG_DIR", str(tmp_path / "logs"))
    output_path = tmp_path / "whales.json"
    database_path = output_path.with_suffix(".sqlite3")
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    profile = _profile(output_path)
    _create_test_schema(database_path)
    now = datetime(2026, 5, 20, tzinfo=UTC)
    FrozenDateTime.frozen_now = now
    wallets = [WALLET_ONE, WALLET_TWO, WALLET_THREE, WALLET_FOUR]
    whales = {
        wallet: _tracked_whale_payload(
            wallet,
            current_position_value=current_position_value,
        )
        for wallet, current_position_value in zip(wallets, [10, 20, 30, 40])
    }

    async def fake_fetch_candidate_entries(
        self: WhaleTracker,
        client: Any,
    ) -> CandidateEntries:
        return CandidateEntries(
            pnl_entries={},
            vol_entries={},
            candidates=[
                Candidate(
                    proxy_wallet=wallet,
                    source="core",
                    matched_pools=["core"],
                )
                for wallet in wallets
            ],
            pool_summary=Counter({"core": len(wallets)}),
        )

    async def fake_process_candidate_batches(
        self: WhaleTracker,
        client: Any,
        entries: CandidateEntries,
        now: datetime,
    ) -> CandidateScan:
        return CandidateScan(
            whales=whales,
            reject_summary=Counter(),
            reject_group_summary={},
            checked_wallet_count=len(entries.candidates),
            checked_group_summary=Counter({"core": len(entries.candidates)}),
        )

    monkeypatch.setattr(tracker_module, "HTTPClient", FakeHTTPClient)
    monkeypatch.setattr(tracker_module, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        WhaleTracker,
        "_fetch_candidate_entries",
        fake_fetch_candidate_entries,
    )
    monkeypatch.setattr(
        WhaleTracker,
        "_process_candidate_batches",
        fake_process_candidate_batches,
    )

    result = asyncio.run(
        WhaleTracker(profile=profile).run(
            run_id="ranked-run",
            started_at=now,
        )
    )

    assert list(result.whales) == [WALLET_TWO, WALLET_THREE, WALLET_FOUR]
    assert result.accepted_wallet_count == 3
    assert result.scoring_method == "percentile_v1"
    assert result.scoring_criteria["current_position_value"] is True

    report_files = list(tmp_path.glob("whales_report_*.json"))
    assert len(report_files) == 1
    report_payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert report_payload["metadata"]["wallet_count"] == 3
    assert report_payload["candidate_funnel"]["accepted_count"] == 3

    engine = create_database_engine(database_path)
    with Session(engine) as session:
        run_row = session.execute(
            select(WhaleTrackerRun).where(WhaleTrackerRun.run_id == "ranked-run")
        ).scalar_one()
        persisted_wallets = session.execute(
            select(TrackedWhale.proxy_wallet)
            .where(TrackedWhale.run_id == "ranked-run")
            .order_by(TrackedWhale.current_position_value)
        ).scalars().all()

    assert run_row.accepted_wallet_count == 3
    assert persisted_wallets == [WALLET_TWO, WALLET_THREE, WALLET_FOUR]


def test_load_default_workflow_profile() -> None:
    profile = load_workflow_profile()

    assert profile.profile_version == "whale_tracking_v2"
    assert profile.candidate_pool.top_n == 250
    assert profile.activity.trade_count_window_days == 30
    assert profile.activity.last_activity_max_age_days == 7


def test_load_quality_workflow_profile() -> None:
    profile = load_workflow_profile(QUALITY_PROFILE_PATH)

    assert profile.profile_version == "whale_tracking_quality_v1"
    assert profile.target_wallet_count == 500
    assert profile.filters.min_roi == 0.05
    assert profile.filters.min_profit_factor == 2.0
    assert profile.filters.max_largest_win_share == 0.60


def test_resolve_project_path_uses_repo_root_for_relative_paths() -> None:
    resolved_path = _resolve_project_path(
        "data/reports/track_whales/polymarket_whales.json"
    )

    assert resolved_path == (
        PROJECT_ROOT
        / "data/reports/track_whales/polymarket_whales.json"
    )


def test_settings_provide_default_project_data_sqlite() -> None:
    profile = WhaleTrackingProfile()

    assert not hasattr(profile, "database_path")
    assert DEFAULT_SQLITE_PATH == (
        PROJECT_ROOT
        / "data/db/"
        "void_liquidity.sqlite3"
    )
    assert get_settings().database.sqlite_path == DEFAULT_SQLITE_PATH
    assert get_settings().database.database_url == f"sqlite:///{DEFAULT_SQLITE_PATH}"


def test_database_session_does_not_create_tables_implicitly(tmp_path: Path) -> None:
    database_path = tmp_path / "whales.sqlite3"

    with database_session(database_path) as session:
        with pytest.raises(OperationalError):
            session.execute(select(WhaleTrackerRun)).all()


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


def test_fetch_all_activity_returns_fetch_error_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VOID_LIQUIDITY_LOG_DIR", str(tmp_path / "logs"))
    output_path = tmp_path / "whales.json"
    profile = _profile(output_path)

    async def fake_get_activity(
        client: Any,
        params: ActivityParams,
    ) -> list[dict[str, Any]]:
        raise RuntimeError("api down")

    monkeypatch.setattr(tracker_module, "get_activity", fake_get_activity)

    result = asyncio.run(
        WhaleTracker(profile=profile)._fetch_all_activity(
            client=FakeHTTPClient(),
            proxy_wallet=WALLET_ONE,
            start=datetime(2026, 5, 1, tzinfo=UTC),
            end=datetime(2026, 5, 20, tzinfo=UTC),
        )
    )

    assert result.rows == []
    assert result.complete is False
    assert result.error_type == "RuntimeError"
    assert result.error == "api down"
    assert result.error_context["request_type"] == "activity"
    assert result.error_context["proxy_wallet"] == WALLET_ONE
    assert result.error_context["offset"] == 0
    assert result.error_context["is_rate_limited"] is False


def test_incomplete_activity_is_not_a_reject_reason_when_volume_passes(
    tmp_path: Path,
) -> None:
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
            "closed_positions_pnl": 1,
            "roi": 0.1,
            "profit_factor": 1.5,
            "largest_win_share": 0.5,
        },
        activity_metrics={
            "activity_complete": False,
            "activity_capped": True,
            "trade_count_window": 3500,
            "activity_volume_window": 10_000,
            "last_activity_age_days": 0.1,
        },
    )

    assert reasons == []


def test_capped_activity_still_requires_minimum_volume(tmp_path: Path) -> None:
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
            "closed_positions_pnl": 1,
            "roi": 0.1,
            "profit_factor": 1.5,
            "largest_win_share": 0.5,
        },
        activity_metrics={
            "activity_complete": False,
            "activity_capped": True,
            "trade_count_window": 3500,
            "activity_volume_window": 9_999,
            "last_activity_age_days": 0.1,
        },
    )

    assert reasons == ["activity_volume_below_min"]


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
            {"realizedPnl": 30, "totalBought": 100, "avgPrice": 0.5},
            {"realizedPnl": 10, "totalBought": 100, "avgPrice": 0.5},
            {"realizedPnl": -20, "totalBought": 100, "avgPrice": 0.5},
        ],
        is_complete=True,
        unknown_timestamp_count=0,
    )

    assert metrics["closed_positions_cost_basis"] == 150
    assert metrics["roi"] == pytest.approx(20 / 150)
    assert metrics["roi_available"] is True
    assert metrics["gross_profit"] == 40
    assert metrics["gross_loss"] == 20
    assert metrics["profit_factor"] == 2
    assert metrics["avg_win"] == 20
    assert metrics["avg_loss"] == 20
    assert metrics["largest_win"] == 30
    assert metrics["largest_win_share"] == pytest.approx(30 / 40)
    assert metrics["largest_loss"] == 20


def test_closed_position_metrics_mark_largest_win_share_unavailable() -> None:
    metrics = _aggregate_closed_positions(
        closed_positions=[
            {"realizedPnl": -10, "totalBought": 100, "avgPrice": 0.5},
            {"realizedPnl": 0, "totalBought": 100, "avgPrice": 0.5},
        ],
        is_complete=True,
        unknown_timestamp_count=0,
    )

    assert metrics["gross_profit"] == 0
    assert metrics["largest_win"] == 0
    assert metrics["largest_win_share"] is None


def test_closed_position_metrics_mark_truncated_samples() -> None:
    metrics = _aggregate_closed_positions(
        closed_positions=[{"realizedPnl": 1, "totalBought": 10, "avgPrice": 0.5}],
        is_complete=True,
        unknown_timestamp_count=0,
        is_truncated=True,
    )

    assert metrics["closed_positions_complete"] is True
    assert metrics["closed_positions_truncated"] is True


def test_closed_position_metrics_mark_roi_unavailable_without_cost_basis() -> None:
    metrics = _aggregate_closed_positions(
        closed_positions=[{"realizedPnl": 10}],
        is_complete=True,
        unknown_timestamp_count=0,
    )

    assert metrics["closed_positions_cost_basis"] == 0
    assert metrics["roi"] is None
    assert metrics["roi_available"] is False


def test_qualification_rejects_unavailable_roi(tmp_path: Path) -> None:
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
            "closed_positions_pnl": 1,
            "roi": None,
            "profit_factor": 2,
            "largest_win_share": 0.5,
        },
        activity_metrics={
            "activity_capped": False,
            "trade_count_window": 10,
            "activity_volume_window": 10_000,
            "last_activity_age_days": 0.1,
        },
    )

    assert reasons == ["roi_unavailable"]


def test_qualification_rejects_low_profit_factor(tmp_path: Path) -> None:
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
            "closed_positions_pnl": 1,
            "roi": 0.1,
            "profit_factor": 1.49,
            "largest_win_share": 0.5,
        },
        activity_metrics={
            "activity_capped": False,
            "trade_count_window": 10,
            "activity_volume_window": 10_000,
            "last_activity_age_days": 0.1,
        },
    )

    assert reasons == ["profit_factor_below_min"]


def test_qualification_rejects_lucky_shot_largest_win_share(tmp_path: Path) -> None:
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
            "closed_positions_pnl": 1,
            "roi": 0.1,
            "profit_factor": 1.5,
            "largest_win_share": 0.61,
        },
        activity_metrics={
            "activity_capped": False,
            "trade_count_window": 10,
            "activity_volume_window": 10_000,
            "last_activity_age_days": 0.1,
        },
    )

    assert reasons == ["largest_win_share_above_max"]


def test_qualification_allows_largest_win_share_at_limit(tmp_path: Path) -> None:
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
            "closed_positions_pnl": 1,
            "roi": 0.1,
            "profit_factor": 1.5,
            "largest_win_share": 0.60,
        },
        activity_metrics={
            "activity_capped": False,
            "trade_count_window": 10,
            "activity_volume_window": 10_000,
            "last_activity_age_days": 0.1,
        },
    )

    assert reasons == []


def test_report_payload_includes_group_funnel_and_metric_summaries(
    tmp_path: Path,
) -> None:
    profile = _profile(tmp_path / "whales.json")
    generated_at = datetime(2026, 5, 20, tzinfo=UTC)
    whales = {
        WALLET_ONE: {
            "metadata": {
                "proxy_wallet": WALLET_ONE,
                "user_name": "core",
                "x_username": "",
                "verified_badge": False,
            },
            "metrics": {
                "leaderboard": {
                    "candidate_pool_source": "core",
                    "matched_pools": ["core", "pnl_top", "volume_top"],
                    "pnl_rank": "1",
                    "vol_rank": "1",
                    "leaderboard_pnl": 100,
                    "leaderboard_volume": 1_000,
                },
                "exposure": {
                    "open_position_count": 2,
                    "current_position_value": 10_000,
                    "largest_position_value": 6_000,
                    "position_concentration": 0.6,
                },
                "closed_positions": {
                    "closed_trade_count": 50,
                    "closed_positions_pnl": 100,
                    "closed_positions_cost_basis": 500,
                    "roi": 0.2,
                    "roi_available": True,
                    "profit_factor": 2,
                    "gross_profit": 200,
                    "gross_loss": 100,
                    "avg_win": 20,
                    "avg_loss": 10,
                    "largest_win": 50,
                    "largest_win_share": 0.25,
                    "largest_loss": 30,
                    "closed_positions_truncated": False,
                },
                "activity": {
                    "trade_count_window": 10,
                    "trade_count_7d": 5,
                    "activity_volume_window": 10_000,
                    "activity_volume_7d": 5_000,
                    "last_activity_at": generated_at.isoformat(),
                    "last_activity_age_days": 0,
                    "activity_complete": True,
                    "activity_capped": False,
                },
            },
        },
        WALLET_TWO: {
            "metadata": {
                "proxy_wallet": WALLET_TWO,
                "user_name": "specialist",
                "x_username": "",
                "verified_badge": False,
            },
            "metrics": {
                "leaderboard": {
                    "candidate_pool_source": "pnl_specialist",
                    "matched_pools": ["pnl_top"],
                    "pnl_rank": "2",
                    "vol_rank": None,
                    "leaderboard_pnl": 200,
                    "leaderboard_volume": 0,
                },
                "exposure": {
                    "open_position_count": 4,
                    "current_position_value": 20_000,
                    "largest_position_value": 5_000,
                    "position_concentration": 0.25,
                },
                "closed_positions": {
                    "closed_trade_count": 100,
                    "closed_positions_pnl": 300,
                    "closed_positions_cost_basis": 600,
                    "roi": 0.5,
                    "roi_available": True,
                    "profit_factor": 3,
                    "gross_profit": 450,
                    "gross_loss": 150,
                    "avg_win": 30,
                    "avg_loss": 15,
                    "largest_win": 80,
                    "largest_win_share": 0.17777777777777778,
                    "largest_loss": 40,
                    "closed_positions_truncated": True,
                },
                "activity": {
                    "trade_count_window": 20,
                    "trade_count_7d": 10,
                    "activity_volume_window": 20_000,
                    "activity_volume_7d": 10_000,
                    "last_activity_at": generated_at.isoformat(),
                    "last_activity_age_days": 1,
                    "activity_complete": False,
                    "activity_capped": True,
                },
            },
        },
    }

    report = build_report_payload(
        profile=profile,
        whales=whales,
        reject_summary=Counter({"current_position_value_below_min": 1}),
        reject_group_summary={
            "core": Counter({"current_position_value_below_min": 1}),
        },
        checked_wallet_count=3,
        checked_group_summary=Counter({"core": 2, "pnl_specialist": 1}),
        candidate_wallet_count=3,
        candidate_pool_summary=Counter({"core": 2, "pnl_specialist": 1}),
        generated_at=generated_at,
        run_id="test-run",
    )

    assert report["metadata"]["run_id"] == "test-run"
    assert report["candidate_funnel"]["acceptance_rate"] == pytest.approx(2 / 3)
    assert report["candidate_funnel"]["by_group"]["core"] == {
        "candidate_count": 2,
        "checked_count": 2,
        "accepted_count": 1,
        "acceptance_rate": 0.5,
        "reject_summary": {"current_position_value_below_min": 1},
    }
    assert report["metric_quality_summary"] == {
        "activity_capped_count": 1,
        "closed_positions_truncated_count": 1,
        "roi_unavailable_count": 0,
    }
    assert report["accepted_metrics"]["overall"]["closed_positions.roi"] == {
        "count": 2,
        "avg": 0.35,
        "median": 0.35,
        "p25": 0.275,
        "p75": 0.425,
        "min": 0.2,
        "max": 0.5,
    }
    assert report["accepted_metrics"]["by_group"]["core"][
        "closed_positions.roi"
    ]["median"] == 0.2
    assert report["near_threshold_counts"]["roi_margin"] == 0
    assert report["outlier_summary"]["roi"]["top"][0]["proxy_wallet"] == WALLET_TWO
