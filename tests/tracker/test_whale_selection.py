import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.engine import make_url

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine, database_session
from whale_tracker.settings import get_settings
from whale_tracker.tracker.whales.models import (
    PolymarketWhale,
    WhaleObservation,
    WhaleRun,
)
from whale_tracker.tracker.whales.repository import list_tracked_whale_wallets


NOW = datetime(2026, 6, 1, tzinfo=UTC)
WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
WALLET_THREE = "0xcccccccccccccccccccccccccccccccccccccccc"


def test_tracked_whale_selection_requires_three_completed_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    _insert_whale_runs(
        database_url,
        [
            ("run-1", NOW, "completed", [WALLET_ONE]),
            ("run-2", NOW + timedelta(hours=1), "completed", [WALLET_ONE]),
        ],
    )

    assert list_tracked_whale_wallets() == []


def test_tracked_whale_selection_keeps_wallets_seen_in_last_three_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    _insert_whale_runs(
        database_url,
        [
            ("run-1", NOW, "completed", [WALLET_ONE, WALLET_TWO]),
            ("run-2", NOW + timedelta(hours=1), "completed", [WALLET_ONE]),
            ("run-3", NOW + timedelta(hours=2), "completed", [WALLET_ONE, WALLET_THREE]),
        ],
    )

    assert list_tracked_whale_wallets() == [WALLET_ONE]


def test_tracked_whale_selection_ignores_runs_outside_latest_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    _insert_whale_runs(
        database_url,
        [
            ("run-1", NOW, "completed", [WALLET_ONE, WALLET_TWO]),
            ("run-2", NOW + timedelta(hours=1), "completed", [WALLET_ONE]),
            ("run-3", NOW + timedelta(hours=2), "completed", [WALLET_ONE]),
            ("run-4", NOW + timedelta(hours=3), "completed", [WALLET_TWO]),
        ],
    )

    assert list_tracked_whale_wallets() == []


def test_tracked_whale_selection_uses_only_completed_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    _insert_whale_runs(
        database_url,
        [
            ("run-1", NOW, "completed", [WALLET_ONE]),
            ("run-2", NOW + timedelta(hours=1), "completed", [WALLET_ONE]),
            ("run-3", NOW + timedelta(hours=2), "failed", [WALLET_ONE]),
            ("run-4", NOW + timedelta(hours=3), "completed", [WALLET_ONE]),
        ],
    )

    assert list_tracked_whale_wallets() == [WALLET_ONE]


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


def _insert_whale_runs(
    database_url: str,
    runs: list[tuple[str, datetime, str, list[str]]],
) -> None:
    with database_session(database_url) as session:
        wallets = sorted({wallet for _, _, _, run_wallets in runs for wallet in run_wallets})
        whales = {
            wallet: PolymarketWhale(
                proxy_wallet=wallet,
                identity={"proxy_wallet": wallet},
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
            for wallet in wallets
        }
        session.add_all(whales.values())
        session.flush()

        for run_id, generated_at, status, run_wallets in runs:
            session.add(
                WhaleRun(
                    run_id=run_id,
                    status=status,
                    profile_version="test",
                    started_at=generated_at,
                    finished_at=generated_at,
                    generated_at=generated_at,
                    checked_wallet_count=len(run_wallets),
                    observed_wallet_count=len(run_wallets),
                )
            )
            session.flush()
            session.add_all(
                [
                    WhaleObservation(
                        run_id=run_id,
                        whale_id=whales[wallet].id,
                        metrics={"candidate_source": "both"},
                        generated_at=generated_at,
                    )
                    for wallet in run_wallets
                ]
            )

        session.commit()


def _set_database_env(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    parsed_url = make_url(database_url)
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_DB", parsed_url.database or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_USER", parsed_url.username or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PASSWORD", parsed_url.password or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_HOST", parsed_url.host or "")
    monkeypatch.setenv("WHALE_TRACKER_POSTGRES_PORT", str(parsed_url.port or 5432))
