from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.candidates.models import (
    WhaleMarket,
    WhaleMarketCandidateRun,
    WhaleMarketMetricSnapshot,
)
from void_liquidity.adapters.polymarket.markets.whales.candidates.repository import (
    get_latest_market_candidate_run,
    list_latest_market_candidates,
    list_market_snapshots,
    persist_market_candidates,
)
from void_liquidity.data.base import Base
from void_liquidity.data.engine import create_database_engine, database_session
from void_liquidity.settings import get_settings


NOW = datetime(2026, 5, 28, tzinfo=UTC)


def test_persist_market_candidates_ignores_empty_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    persist_market_candidates(
        [],
        run_id="run-empty",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=0,
        error_count=0,
    )

    with database_session() as session:
        run = session.scalar(select(WhaleMarketCandidateRun))
        markets = session.scalars(select(WhaleMarket)).all()
        snapshots = session.scalars(select(WhaleMarketMetricSnapshot)).all()

    assert run is not None
    assert run.run_id == "run-empty"
    assert run.candidate_count == 0
    assert markets == []
    assert snapshots == []


def test_persist_market_candidates_inserts_candidate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)

    persist_market_candidates(
        [_candidate()],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=1,
        seen_at=NOW,
    )

    with database_session(database_path) as session:
        run = session.scalar(select(WhaleMarketCandidateRun))
        market = session.scalar(select(WhaleMarket))
        snapshot = session.scalar(select(WhaleMarketMetricSnapshot))

    assert run is not None
    assert run.run_id == "run-1"
    assert run.generated_at == _sqlite_datetime(NOW)
    assert run.min_whale_count == 3
    assert run.candidate_count == 1
    assert run.position_count == 10
    assert run.error_count == 1
    assert market is not None
    assert market.token_id == "token-1"
    assert market.condition_id == "0x" + "1" * 64
    assert market.title == "Will this happen?"
    assert market.slug == "will-this-happen"
    assert market.outcome == "Yes"
    assert market.opposite_token_id == "token-2"
    assert market.opposite_outcome == "No"
    assert market.end_date == date(2026, 7, 20)
    assert market.negative_risk is False
    assert market.first_seen_at == _sqlite_datetime(NOW)
    assert market.last_seen_at == _sqlite_datetime(NOW)
    assert snapshot is not None
    assert snapshot.run_id == "run-1"
    assert snapshot.token_id == "token-1"
    assert snapshot.whale_count == 3
    assert snapshot.wallets == ["wallet-1", "wallet-2", "wallet-3"]
    assert snapshot.total_size == 30
    assert snapshot.total_current_value == 15
    assert snapshot.weighted_avg_price == 0.4
    assert snapshot.cur_price == 0.5
    assert snapshot.generated_at == _sqlite_datetime(NOW)


def test_persist_market_candidates_updates_existing_candidate_on_token_conflict(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    later = datetime(2026, 5, 29, tzinfo=UTC)

    persist_market_candidates(
        [_candidate()],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=0,
        seen_at=NOW,
    )
    persist_market_candidates(
        [
            _candidate(
                title="Updated title",
                whale_count=4,
                total_current_value=25,
                wallets=["wallet-1", "wallet-2", "wallet-3", "wallet-4"],
                cur_price=0.6,
            )
        ],
        run_id="run-2",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=12,
        error_count=0,
        seen_at=later,
    )

    with database_session(database_path) as session:
        runs = session.scalars(
            select(WhaleMarketCandidateRun).order_by(WhaleMarketCandidateRun.run_id)
        ).all()
        markets = session.scalars(select(WhaleMarket)).all()
        snapshots = session.scalars(
            select(WhaleMarketMetricSnapshot).order_by(WhaleMarketMetricSnapshot.run_id)
        ).all()

    assert [run.run_id for run in runs] == ["run-1", "run-2"]
    assert len(markets) == 1
    market = markets[0]
    assert market.title == "Updated title"
    assert market.first_seen_at == _sqlite_datetime(NOW)
    assert market.last_seen_at == _sqlite_datetime(later)
    assert len(snapshots) == 2
    assert snapshots[0].run_id == "run-1"
    assert snapshots[0].whale_count == 3
    assert snapshots[0].total_current_value == 15
    assert snapshots[1].run_id == "run-2"
    assert snapshots[1].whale_count == 4
    assert snapshots[1].total_current_value == 25
    assert snapshots[1].wallets == ["wallet-1", "wallet-2", "wallet-3", "wallet-4"]
    assert snapshots[1].cur_price == 0.6


def test_persist_market_candidates_rejects_duplicate_run_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    persist_market_candidates(
        [_candidate()],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=0,
        seen_at=NOW,
    )

    with pytest.raises(IntegrityError):
        persist_market_candidates(
            [_candidate(whale_count=5, total_current_value=35)],
            run_id="run-1",
            selection_run_id="selection-run",
            min_whale_count=4,
            position_count=12,
            error_count=1,
            seen_at=NOW,
        )


def test_get_latest_market_candidate_run_returns_none_without_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    assert get_latest_market_candidate_run() is None


def test_get_latest_market_candidate_run_returns_newest_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)
    later = datetime(2026, 5, 29, tzinfo=UTC)

    persist_market_candidates(
        [_candidate()],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=0,
        seen_at=NOW,
    )
    persist_market_candidates(
        [_candidate(token_id="token-2", total_current_value=25)],
        run_id="run-2",
        selection_run_id="selection-run",
        min_whale_count=4,
        position_count=12,
        error_count=1,
        seen_at=later,
    )

    run = get_latest_market_candidate_run()

    assert run is not None
    assert run.run_id == "run-2"
    assert run.generated_at == _sqlite_datetime(later)
    assert run.min_whale_count == 4
    assert run.candidate_count == 1
    assert run.position_count == 12
    assert run.error_count == 1


def test_list_latest_market_candidates_returns_empty_list_without_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    assert list_latest_market_candidates() == []


def test_list_latest_market_candidates_returns_latest_run_candidates_sorted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)
    later = datetime(2026, 5, 29, tzinfo=UTC)

    persist_market_candidates(
        [_candidate()],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=0,
        seen_at=NOW,
    )
    persist_market_candidates(
        [
            _candidate(
                token_id="token-2",
                whale_count=4,
                total_current_value=20,
            ),
            _candidate(
                token_id="token-3",
                whale_count=5,
                total_current_value=10,
            ),
            _candidate(
                token_id="token-4",
                whale_count=4,
                total_current_value=30,
            ),
        ],
        run_id="run-2",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=12,
        error_count=0,
        seen_at=later,
    )

    candidates = list_latest_market_candidates()

    assert [candidate.token_id for candidate in candidates] == [
        "token-3",
        "token-4",
        "token-2",
    ]
    assert candidates[0].whale_count == 5
    assert candidates[0].total_current_value == 10
    assert candidates[0].condition_id == "0x" + "1" * 64


def test_list_latest_market_candidates_applies_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    persist_market_candidates(
        [
            _candidate(token_id="token-1", whale_count=3),
            _candidate(token_id="token-2", whale_count=4),
        ],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=0,
        seen_at=NOW,
    )

    candidates = list_latest_market_candidates(limit=1)

    assert [candidate.token_id for candidate in candidates] == ["token-2"]


def test_list_market_snapshots_returns_token_history_newest_first(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)
    later = datetime(2026, 5, 29, tzinfo=UTC)

    persist_market_candidates(
        [_candidate()],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=0,
        seen_at=NOW,
    )
    persist_market_candidates(
        [
            _candidate(whale_count=4, total_current_value=25),
            _candidate(token_id="token-2", whale_count=5, total_current_value=35),
        ],
        run_id="run-2",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=12,
        error_count=0,
        seen_at=later,
    )

    snapshots = list_market_snapshots("token-1")

    assert [snapshot.run_id for snapshot in snapshots] == ["run-2", "run-1"]
    assert [snapshot.generated_at for snapshot in snapshots] == [
        _sqlite_datetime(later),
        _sqlite_datetime(NOW),
    ]
    assert snapshots[0].token_id == "token-1"
    assert snapshots[0].whale_count == 4
    assert snapshots[0].total_current_value == 25
    assert snapshots[0].title == "Will this happen?"


def test_list_market_snapshots_returns_empty_list_for_unknown_token(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    persist_market_candidates(
        [_candidate()],
        run_id="run-1",
        selection_run_id="selection-run",
        min_whale_count=3,
        position_count=10,
        error_count=0,
        seen_at=NOW,
    )

    assert list_market_snapshots("unknown-token") == []


def _prepare_database(monkeypatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path


def _candidate(
    *,
    token_id: str = "token-1",
    title: str = "Will this happen?",
    whale_count: int = 3,
    total_current_value: float = 15,
    wallets: list[str] | None = None,
    cur_price: float = 0.5,
) -> MarketCandidate:
    return MarketCandidate(
        token_id=token_id,
        condition_id="0x" + "1" * 64,
        title=title,
        slug="will-this-happen",
        outcome="Yes",
        whale_count=whale_count,
        wallets=wallets or ["wallet-1", "wallet-2", "wallet-3"],
        total_size=30,
        total_current_value=total_current_value,
        weighted_avg_price=0.4,
        cur_price=cur_price,
        opposite_token_id="token-2",
        opposite_outcome="No",
        end_date=date(2026, 7, 20),
        negative_risk=False,
    )


def _sqlite_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=None)
