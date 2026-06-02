import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine, database_session
from whale_tracker.settings import get_settings
from whale_tracker.tracker.markets import service as service_module
from whale_tracker.tracker.markets.domain import Market, WhalePosition
from whale_tracker.tracker.markets.filter import (
    MarketFilterProfile,
    build_market_candidates,
)
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    MarketMetricSnapshot,
    MarketRun,
)
from whale_tracker.tracker.markets.scoring import (
    MarketScoringProfile,
    qualify_markets,
)
from whale_tracker.tracker.markets.repository import (
    list_markets,
    list_qualified_markets,
)
from whale_tracker.tracker.markets.service import MarketTrackerService
from whale_tracker.tracker.whales.models import (
    PolymarketWhale,
    WhaleMetric,
    WhaleRun,
)


NOW = datetime(2026, 6, 1, tzinfo=UTC)
WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
CONDITION_ID = "0x" + "1" * 64
YES_TOKEN = "111"
NO_TOKEN = "222"


class FakeDataClient:
    async def get_current_positions(self, params: Any) -> list[dict[str, Any]]:
        if params.user == WALLET_ONE:
            return [_position(asset=YES_TOKEN, current_value=100, size=10)]

        return [
            _position(asset=YES_TOKEN, current_value=50, size=5),
            _position(asset=NO_TOKEN, outcome="No", current_value=25, size=5),
        ]


def test_build_market_candidates_groups_and_filters() -> None:
    candidates = build_market_candidates(
        [
            _whale_position(WALLET_ONE, token_id=YES_TOKEN, current_value=100, size=10),
            _whale_position(WALLET_TWO, token_id=YES_TOKEN, current_value=50, size=5),
            _whale_position(WALLET_ONE, token_id=NO_TOKEN, current_value=75, size=15),
        ],
        min_whale_count=2,
    )

    assert [candidate.token_id for candidate in candidates] == [YES_TOKEN]
    assert candidates[0].whale_count == 2
    assert candidates[0].wallets == [WALLET_ONE, WALLET_TWO]
    assert candidates[0].total_current_value == 150
    assert candidates[0].weighted_avg_price == 0.4


def test_qualify_markets_marks_matching_profiles() -> None:
    markets = qualify_markets(
        [
            _market(token_id="confirmed", weighted_avg_price=0.4, cur_price=0.5),
            _market(token_id="pain", weighted_avg_price=0.6, cur_price=0.5),
        ],
        profiles=(
            MarketScoringProfile(name="confirmed"),
            MarketScoringProfile(name="pain"),
        ),
    )

    assert markets[0].qualified is True
    assert markets[0].categories == ["confirmed"]
    assert markets[1].qualified is True
    assert markets[1].categories == ["pain"]


def test_market_tracker_run_persists_markets_and_qualified_markets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    _insert_selection_run(database_path)
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(),
    )
    service = MarketTrackerService(
        filter_profile=MarketFilterProfile(min_whale_count=2),
        scoring_profile=(MarketScoringProfile(name="high_value"),),
    )

    result = asyncio.run(service.run(whales_run_id="selection-run-1", now=NOW))

    assert result.run_id.endswith("-markets")
    assert [market.token_id for market in result.markets] == [YES_TOKEN]
    assert [market.token_id for market in result.qualified_markets] == [YES_TOKEN]
    assert result.scored_markets is not None

    with database_session(database_path) as session:
        run = session.scalar(select(MarketRun))
        identity = session.scalar(select(MarketIdentity))
        snapshot = session.scalar(select(MarketMetricSnapshot))

    assert run is not None
    assert run.whales_run_id == "selection-run-1"
    assert run.filter_profile == "default_market_filter"
    assert run.scoring_profile == "qualified_market_profiles"
    assert run.checked_market_count == 2
    assert run.filtered_market_count == 1
    assert run.scored_market_count == 1
    assert run.removed_market_count == 0
    assert identity is not None
    assert identity.token_id == YES_TOKEN
    assert snapshot is not None
    assert snapshot.score == 150
    assert snapshot.metrics["whale_count"] == 2
    assert snapshot.metrics["total_current_value"] == 150

    listed_markets = list_markets(run_id=result.run_id)
    listed_qualified = list_qualified_markets(run_id=result.run_id)

    assert [market.token_id for market in listed_markets] == [YES_TOKEN]
    assert [market.token_id for market in listed_qualified] == [YES_TOKEN]


def test_market_repository_upserts_identity_and_appends_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    _insert_selection_run(database_path)
    service = MarketTrackerService(
        filter_profile=MarketFilterProfile(min_whale_count=1),
        scoring_profile=(MarketScoringProfile(name="high_value"),),
    )
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(),
    )

    first = asyncio.run(service.run(whales_run_id="selection-run-1", now=NOW))
    later = datetime(2026, 6, 2, tzinfo=UTC)
    second = asyncio.run(service.run(whales_run_id="selection-run-1", now=later))

    with database_session(database_path) as session:
        identities = session.scalars(select(MarketIdentity)).all()
        snapshots = session.scalars(
            select(MarketMetricSnapshot)
            .where(MarketMetricSnapshot.market.has(token_id=YES_TOKEN))
            .order_by(MarketMetricSnapshot.run_id)
        ).all()

    assert len([item for item in identities if item.token_id == YES_TOKEN]) == 1
    assert [snapshot.run_id for snapshot in snapshots] == [
        first.run_id,
        second.run_id,
    ]


def test_market_tracker_run_without_scoring_persists_filtered_markets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    _insert_selection_run(database_path)
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(),
    )
    service = MarketTrackerService(
        filter_profile=MarketFilterProfile(min_whale_count=2),
    )

    result = asyncio.run(service.run(whales_run_id="selection-run-1", now=NOW))

    assert result.scored_markets is None
    assert [market.token_id for market in result.markets] == [YES_TOKEN]
    assert result.qualified_markets == []

    with database_session(database_path) as session:
        run = session.scalar(select(MarketRun))
        snapshot = session.scalar(select(MarketMetricSnapshot))

    assert run is not None
    assert run.scoring_profile == ""
    assert run.filtered_market_count == 1
    assert run.scored_market_count == 1
    assert snapshot is not None
    assert snapshot.score == 0.0
    assert snapshot.metrics["whale_count"] == 2


def _prepare_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "markets.sqlite3"
    get_settings.cache_clear()
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path


def _insert_selection_run(database_path: Path) -> None:
    with database_session(database_path) as session:
        session.add(
            WhaleRun(
                run_id="selection-run-1",
                status="completed",
                profile_version="test",
                started_at=NOW,
                finished_at=NOW,
                generated_at=NOW,
                filter_profile="test_filter",
                scoring_profile="test_scoring",
                checked_wallet_count=2,
                filtered_wallet_count=2,
                scored_wallet_count=2,
                removed_wallet_count=0,
            )
        )
        one = PolymarketWhale(
            proxy_wallet=WALLET_ONE,
            identity={"proxy_wallet": WALLET_ONE},
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        two = PolymarketWhale(
            proxy_wallet=WALLET_TWO,
            identity={"proxy_wallet": WALLET_TWO},
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        session.add_all([one, two])
        session.flush()
        session.add_all(
            [
                WhaleMetric(
                    run_id="selection-run-1",
                    whale_id=one.id,
                    score=1.0,
                    metrics={},
                    generated_at=NOW,
                ),
                WhaleMetric(
                    run_id="selection-run-1",
                    whale_id=two.id,
                    score=0.5,
                    metrics={},
                    generated_at=NOW,
                ),
            ]
        )
        session.commit()


def _whale_position(
    proxy_wallet: str,
    *,
    token_id: str,
    outcome: str = "Yes",
    current_value: float = 100,
    size: float = 10,
) -> WhalePosition:
    return WhalePosition(
        proxy_wallet=proxy_wallet,
        token_id=token_id,
        condition_id=CONDITION_ID,
        outcome=outcome,
        title="Will this happen?",
        slug="will-this-happen",
        size=size,
        current_value=current_value,
        avg_price=0.4,
        cur_price=0.5,
        opposite_token_id=NO_TOKEN,
        opposite_outcome="No",
        end_date=date(2026, 7, 20),
    )


def _market(
    *,
    token_id: str,
    weighted_avg_price: float = 0.4,
    cur_price: float = 0.5,
    total_current_value: float = 30,
    whale_count: int = 3,
) -> Market:
    return Market(
        token_id=token_id,
        condition_id=CONDITION_ID,
        title="Will this happen?",
        slug="will-this-happen",
        outcome="Yes",
        whale_count=whale_count,
        wallets=[WALLET_ONE, WALLET_TWO],
        total_size=10,
        total_current_value=total_current_value,
        weighted_avg_price=weighted_avg_price,
        cur_price=cur_price,
        opposite_token_id=NO_TOKEN,
        opposite_outcome="No",
        end_date=date(2026, 7, 20),
    )


def _position(
    *,
    asset: str,
    outcome: str = "Yes",
    current_value: float = 100,
    size: float = 10,
) -> dict[str, Any]:
    return {
        "asset": asset,
        "conditionId": CONDITION_ID,
        "outcome": outcome,
        "outcomeIndex": 0,
        "title": "Will this happen?",
        "slug": "will-this-happen",
        "size": size,
        "currentValue": current_value,
        "avgPrice": 0.4,
        "curPrice": 0.5,
        "oppositeAsset": NO_TOKEN,
        "oppositeOutcome": "No",
        "endDate": "2026-07-20",
        "negativeRisk": False,
    }
