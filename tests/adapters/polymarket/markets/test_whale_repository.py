from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from void_liquidity.adapters.polymarket.discovery.whales.models import (
    TrackedWhale,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.markets.whales.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.models import (
    WhaleMarketCandidate,
)
from void_liquidity.adapters.polymarket.markets.whales.repository import (
    list_tracked_whale_wallets,
    persist_market_candidates,
)
from void_liquidity.data import Base, create_database_engine, database_session
from void_liquidity.settings import get_settings


NOW = datetime(2026, 5, 28, tzinfo=UTC)


def test_list_tracked_whale_wallets_returns_empty_list(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    assert list_tracked_whale_wallets() == []


def test_list_tracked_whale_wallets_returns_wallets_in_insert_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)

    with database_session(database_path) as session:
        session.add(_tracker_run())
        session.add_all(
            [
                TrackedWhale(
                    run_id="run-1",
                    proxy_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    first_seen=NOW,
                    last_seen=NOW,
                ),
                TrackedWhale(
                    run_id="run-1",
                    proxy_wallet="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    first_seen=NOW,
                    last_seen=NOW,
                ),
            ]
        )
        session.commit()

    assert list_tracked_whale_wallets() == [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    ]


def test_persist_market_candidates_ignores_empty_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    persist_market_candidates([])

    with database_session() as session:
        rows = session.scalars(select(WhaleMarketCandidate)).all()

    assert rows == []


def test_persist_market_candidates_inserts_candidate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)

    persist_market_candidates([_candidate()], seen_at=NOW)

    with database_session(database_path) as session:
        row = session.scalar(select(WhaleMarketCandidate))

    assert row is not None
    assert row.token_id == "token-1"
    assert row.condition_id == "0x" + "1" * 64
    assert row.title == "Will this happen?"
    assert row.slug == "will-this-happen"
    assert row.outcome == "Yes"
    assert row.whale_count == 3
    assert row.wallets == ["wallet-1", "wallet-2", "wallet-3"]
    assert row.total_size == 30
    assert row.total_current_value == 15
    assert row.weighted_avg_price == 0.4
    assert row.cur_price == 0.5
    assert row.opposite_token_id == "token-2"
    assert row.opposite_outcome == "No"
    assert row.end_date == date(2026, 7, 20)
    assert row.negative_risk is False
    assert row.first_seen_at == _sqlite_datetime(NOW)
    assert row.last_seen_at == _sqlite_datetime(NOW)


def test_persist_market_candidates_updates_existing_candidate_on_token_conflict(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    later = datetime(2026, 5, 29, tzinfo=UTC)

    persist_market_candidates([_candidate()], seen_at=NOW)
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
        seen_at=later,
    )

    with database_session(database_path) as session:
        rows = session.scalars(select(WhaleMarketCandidate)).all()

    assert len(rows) == 1
    row = rows[0]
    assert row.title == "Updated title"
    assert row.whale_count == 4
    assert row.total_current_value == 25
    assert row.wallets == ["wallet-1", "wallet-2", "wallet-3", "wallet-4"]
    assert row.cur_price == 0.6
    assert row.first_seen_at == _sqlite_datetime(NOW)
    assert row.last_seen_at == _sqlite_datetime(later)


def _prepare_database(monkeypatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path


def _candidate(
    *,
    title: str = "Will this happen?",
    whale_count: int = 3,
    total_current_value: float = 15,
    wallets: list[str] | None = None,
    cur_price: float = 0.5,
) -> MarketCandidate:
    return MarketCandidate(
        token_id="token-1",
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


def _tracker_run() -> WhaleTrackerRun:
    return WhaleTrackerRun(
        run_id="run-1",
        profile_version="test",
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        generated_at=NOW,
        candidate_wallet_count=2,
        checked_wallet_count=2,
        accepted_wallet_count=2,
        profile={},
        report_path=None,
    )
