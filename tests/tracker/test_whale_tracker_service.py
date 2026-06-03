import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine, database_session
from whale_tracker.settings import get_settings
from whale_tracker.tracker.whales import service as service_module
from whale_tracker.tracker.whales.discovery import WhaleDiscoveryProfile
from whale_tracker.tracker.whales.models import PolymarketWhale, WhaleMetric, WhaleRun
from whale_tracker.tracker.whales.scoring import ZScoreWhaleScoringProfile
from whale_tracker.tracker.whales.service import WhaleTrackerService


NOW = datetime(2026, 6, 1, tzinfo=UTC)
WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
CONDITION_ID = "0x" + "1" * 64


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
        return [
            {
                "timestamp": NOW.isoformat(),
                "conditionId": CONDITION_ID,
                "price": 0.5,
                "size": 10,
                "side": "BUY",
                "name": "Trader",
            }
        ]

    async def get_current_positions(self, params: Any) -> list[dict[str, Any]]:
        value = 100 if params.user == WALLET_ONE else 50
        return [{"currentValue": value}]


def test_whale_tracker_run_persists_prefilter_and_afterfilter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
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
        scoring_profile=ZScoreWhaleScoringProfile(bottom_cut_percentile=0.5),
    )

    result = asyncio.run(service.run(now=NOW))

    assert result.filtered_whales.wallet_count == 2
    assert result.scored_whales is not None
    assert [whale.proxy_wallet for whale in result.selected_whales] == [WALLET_ONE]
    assert [ranked.whale.proxy_wallet for ranked in result.removed_whales] == [
        WALLET_TWO
    ]

    with database_session(database_path) as session:
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
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
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

    with database_session(database_path) as session:
        run = session.scalar(select(WhaleRun))
        metrics = list(session.scalars(select(WhaleMetric)))

    assert run is not None
    assert run.filter_profile == "default_whale_filter"
    assert run.scoring_profile == ""
    assert run.filtered_wallet_count == 2
    assert run.scored_wallet_count == 2
    assert run.removed_wallet_count == 0
    assert [metric.score for metric in metrics] == [0.0, 0.0]


def _prepare_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "whales.sqlite3"
    get_settings.cache_clear()
    monkeypatch.setenv("WHALE_TRACKER_SQLITE_PATH", str(database_path))
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path
