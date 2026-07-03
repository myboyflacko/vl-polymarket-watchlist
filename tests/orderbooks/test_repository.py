from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from vl_polymarket_watchlist.core.db.base import Base
from vl_polymarket_watchlist.core.db.models import (
    MarketDiscoveryRun,
    OrderbookCollectionItem,
    OrderbookCollectionRun,
)
from vl_polymarket_watchlist.orderbooks import repository


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_snapshot_collectable_watchlist_reads_only_collectable_tokens(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE VIEW polymarket_watchlist_v AS
                SELECT
                    'condition-1' AS condition_id,
                    'token-1' AS token_id,
                    'slug-1' AS slug,
                    'Title 1' AS title,
                    'Yes' AS outcome,
                    'high' AS priority,
                    '["whale_discovery"]' AS sources,
                    'whale_discovered' AS watchlist_reason,
                    10 AS days_to_expiry,
                    true AS collect_orderbook
                UNION ALL
                SELECT
                    'condition-2',
                    'token-2',
                    'slug-2',
                    'Title 2',
                    'No',
                    'low',
                    '["gamma_active"]',
                    'closed',
                    5,
                    false
                """
            )
        )

    @contextmanager
    def test_session():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(repository, "database_session", test_session)
    repository.create_orderbook_collection_run(
        run_id="orderbooks-run-1",
        started_at=NOW,
        config_json={},
    )

    items = repository.snapshot_collectable_watchlist(
        run_id="orderbooks-run-1",
        selected_at=NOW,
    )

    assert [item.token_id for item in items] == ["token-1"]
    assert items[0].sources == ["whale_discovery"]
    with session_factory() as session:
        rows = session.query(OrderbookCollectionItem).all()

    assert len(rows) == 1


def test_orderbook_readiness_requires_completed_or_partial_discovery(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @contextmanager
    def test_session():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(repository, "database_session", test_session)

    readiness = repository.get_orderbook_readiness(now=NOW)

    assert readiness.ready is False
    assert readiness.reason == "no_completed_discovery_run"


def test_orderbook_readiness_blocks_while_discovery_is_running(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        session.add(_discovery_run(run_id="run-1", status="running", generated_at=NOW))
        session.commit()

    @contextmanager
    def test_session():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(repository, "database_session", test_session)

    readiness = repository.get_orderbook_readiness(now=NOW)

    assert readiness.ready is False
    assert readiness.reason == "discovery_running"


def test_orderbook_readiness_allows_recent_partial_discovery(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        session.add(_discovery_run(run_id="run-1", status="partial", generated_at=NOW))
        session.commit()

    @contextmanager
    def test_session():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(repository, "database_session", test_session)

    readiness = repository.get_orderbook_readiness(now=NOW)

    assert readiness.ready is True
    assert readiness.reason is None


def test_orderbook_readiness_blocks_stale_discovery(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        session.add(
            _discovery_run(
                run_id="run-1",
                status="completed",
                generated_at=NOW - timedelta(hours=25),
            )
        )
        session.commit()

    @contextmanager
    def test_session():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(repository, "database_session", test_session)

    readiness = repository.get_orderbook_readiness(now=NOW, max_age_hours=24)

    assert readiness.ready is False
    assert readiness.reason == "discovery_stale"


def test_skipped_readiness_does_not_create_orderbook_run(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @contextmanager
    def test_session():
        with session_factory() as session:
            yield session

    monkeypatch.setattr(repository, "database_session", test_session)

    readiness = repository.get_orderbook_readiness(now=NOW)

    assert readiness.ready is False
    with session_factory() as session:
        run_ids = list(session.scalars(select(OrderbookCollectionRun.run_id)))

    assert run_ids == []


def _discovery_run(
    *,
    run_id: str,
    status: str,
    generated_at: datetime,
) -> MarketDiscoveryRun:
    return MarketDiscoveryRun(
        run_id=run_id,
        source="whale_discovery",
        source_version="v1",
        status=status,
        started_at=generated_at,
        finished_at=generated_at if status != "running" else None,
        generated_at=generated_at,
        config_json={},
        input_refs_json={},
        checked_count=1,
        observed_count=1,
        error_count=0,
        metadata_json={},
    )
