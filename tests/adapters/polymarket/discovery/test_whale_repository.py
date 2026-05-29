from datetime import UTC, datetime
from pathlib import Path

from void_liquidity.adapters.polymarket.discovery.whales_v2.models import (
    TrackedWhale,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.discovery.whales_v2.repository import (
    list_tracked_whale_wallets,
)
from void_liquidity.data import Base, create_database_engine, database_session
from void_liquidity.settings import get_settings


NOW = datetime(2026, 5, 28, tzinfo=UTC)
LATER = datetime(2026, 5, 29, tzinfo=UTC)


def test_list_tracked_whale_wallets_returns_empty_list(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    assert list_tracked_whale_wallets() == []


def test_list_tracked_whale_wallets_returns_latest_run_wallets_in_insert_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)

    with database_session(database_path) as session:
        session.add_all(
            [
                _tracker_run(run_id="run-1", generated_at=NOW),
                _tracker_run(run_id="run-2", generated_at=LATER),
            ]
        )
        session.add_all(
            [
                TrackedWhale(
                    run_id="run-1",
                    proxy_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    first_seen=NOW,
                    last_seen=NOW,
                ),
                TrackedWhale(
                    run_id="run-2",
                    proxy_wallet="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    first_seen=LATER,
                    last_seen=LATER,
                ),
                TrackedWhale(
                    run_id="run-2",
                    proxy_wallet="0xcccccccccccccccccccccccccccccccccccccccc",
                    first_seen=LATER,
                    last_seen=LATER,
                ),
            ]
        )
        session.commit()

    assert list_tracked_whale_wallets() == [
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "0xcccccccccccccccccccccccccccccccccccccccc",
    ]


def _prepare_database(monkeypatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path


def _tracker_run(*, run_id: str, generated_at: datetime) -> WhaleTrackerRun:
    return WhaleTrackerRun(
        run_id=run_id,
        profile_version="test",
        status="completed",
        started_at=generated_at,
        finished_at=generated_at,
        generated_at=generated_at,
        candidate_wallet_count=2,
        checked_wallet_count=2,
        accepted_wallet_count=2,
        profile={},
        report_path=None,
    )
