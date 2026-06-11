import asyncio
import os
from datetime import UTC, datetime
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
    WhaleObservation,
    WhaleRun,
)
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


def test_whale_tracker_run_persists_leaderboard_observations(
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

    result = asyncio.run(service.run(now=NOW))

    assert result.whales.wallet_count == 2

    with database_session(database_url) as session:
        run = session.scalar(select(WhaleRun))
        whales = list(session.scalars(select(PolymarketWhale)))
        observations = list(session.scalars(select(WhaleObservation)))

    assert run is not None
    assert run.checked_wallet_count == 2
    assert run.observed_wallet_count == 2
    assert run.profile_version == "whale_leaderboard_only_v1"
    assert [whale.proxy_wallet for whale in whales] == [WALLET_ONE, WALLET_TWO]
    assert len(observations) == 2
    assert {observation.metrics["candidate_source"] for observation in observations} == {
        "both"
    }
    assert {observation.generated_at for observation in observations} == {NOW}


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
