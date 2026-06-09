import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine, database_session
from whale_tracker.settings import get_settings
from whale_tracker.tracker.whales import service as service_module
from whale_tracker.tracker.whales.discovery import WhaleDiscoveryProfile
from whale_tracker.tracker.whales.models import (
    PolymarketWhale,
    TrackedWhaleMetric,
    WhaleMetric,
    WhaleRun,
)
from whale_tracker.tracker.whales.scoring import ZScoreWhaleScoringProfile
from whale_tracker.tracker.whales.service import WhaleTrackerService


NOW = datetime(2026, 6, 1, tzinfo=UTC)
WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class FakeDataClient:
    async def get_leaderboard(self, params: Any) -> list[dict[str, Any]]:
        metric_key = "pnl" if params.orderBy == "PNL" else "vol"
        return [
            {
                "proxyWallet": WALLET_ONE,
                "rank": 1,
                metric_key: 100,
                "name": "Wallet One",
            },
            {
                "proxyWallet": WALLET_TWO,
                "rank": 2,
                metric_key: 50,
                "name": "Wallet Two",
            },
        ]

    async def get_trades(self, params: Any) -> list[dict[str, Any]]:
        raise AssertionError("whale discovery must not fetch trades")

    async def get_current_positions(self, params: Any) -> list[dict[str, Any]]:
        raise AssertionError("whale discovery must not fetch current positions")


def test_whale_tracker_run_persists_prefilter_and_afterfilter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(),
    )
    service = WhaleTrackerService(
        discovery_profile=WhaleDiscoveryProfile(
            wallet_count=2,
            leaderboard_limit=2,
            wallet_batch_size=2,
        ),
        scoring_profile=ZScoreWhaleScoringProfile(),
    )

    result = asyncio.run(service.run(now=NOW))

    assert result.filtered_whales.wallet_count == 2
    assert result.scored_whales is not None
    assert [whale.proxy_wallet for whale in result.selected_whales] == [WALLET_ONE]
    assert [ranked.whale.proxy_wallet for ranked in result.removed_whales] == [
        WALLET_TWO
    ]

    with database_session(database_url) as session:
        run = session.scalar(select(WhaleRun))
        whale = session.scalar(select(PolymarketWhale))
        metric = session.scalar(select(WhaleMetric))

    assert run is not None
    assert run.filtered_wallet_count == 2
    assert run.scored_wallet_count == 1
    assert run.removed_wallet_count == 1
    assert whale is not None
    assert whale.proxy_wallet == WALLET_ONE
    assert metric is not None
    assert metric.score > 0


def test_whale_tracker_run_without_scoring_persists_filtered_whales(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(),
    )
    service = WhaleTrackerService(
        discovery_profile=WhaleDiscoveryProfile(
            wallet_count=2,
            leaderboard_limit=2,
            wallet_batch_size=2,
        )
    )
    service.register_scoring(None)

    result = asyncio.run(service.run(now=NOW))

    assert result.filtered_whales.wallet_count == 2
    assert result.scored_whales is None
    assert [whale.proxy_wallet for whale in result.selected_whales] == [
        WALLET_ONE,
        WALLET_TWO,
    ]

    with database_session(database_url) as session:
        run = session.scalar(select(WhaleRun))
        metrics = list(session.scalars(select(WhaleMetric)))

    assert run is not None
    assert run.filter_profile == "default_whale_filter"
    assert run.scoring_profile == ""
    assert run.filtered_wallet_count == 2
    assert run.scored_wallet_count == 2
    assert run.removed_wallet_count == 0
    assert [metric.score for metric in metrics] == [0.0, 0.0]


def test_whale_tracker_tracks_wallets_after_three_consecutive_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(),
    )
    service = WhaleTrackerService(
        discovery_profile=WhaleDiscoveryProfile(
            wallet_count=2,
            leaderboard_limit=2,
            wallet_batch_size=2,
        )
    )

    first = asyncio.run(service.run(now=NOW))
    second = asyncio.run(service.run(now=NOW + timedelta(hours=1)))
    third = asyncio.run(service.run(now=NOW + timedelta(hours=2)))

    assert first.tracked_whales is not None
    assert first.tracked_whales.wallet_count == 0
    assert second.tracked_whales is not None
    assert second.tracked_whales.wallet_count == 0
    assert third.tracked_whales is not None
    assert third.tracked_whales.proxy_wallets() == [WALLET_ONE, WALLET_TWO]

    with database_session(database_url) as session:
        tracked = list(session.scalars(select(TrackedWhaleMetric)))

    assert len(tracked) == 2
    assert {entry.run_id for entry in tracked} == {third.run_id}
    assert {entry.consecutive_runs for entry in tracked} == {3}


def _prepare_database(monkeypatch: pytest.MonkeyPatch) -> str:
    database_url = os.environ.get("WHALE_TRACKER_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("WHALE_TRACKER_TEST_DATABASE_URL is required for DB integration tests.")

    parsed_url = make_url(database_url)
    if "test" not in (parsed_url.database or ""):
        pytest.fail("WHALE_TRACKER_TEST_DATABASE_URL database name must contain 'test'.")

    get_settings.cache_clear()
    _set_database_env(monkeypatch, database_url)
    engine = create_database_engine(database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return database_url


def _set_database_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    parsed_url = make_url(database_url)
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_DB", parsed_url.database or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_USER", parsed_url.username or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PASSWORD", parsed_url.password or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_HOST", parsed_url.host or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PORT", str(parsed_url.port or 5432))
