from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from vl_polymarket_watchlist.core.db.base import Base
from vl_polymarket_watchlist.core.db.models import OrderbookCollectionItem
from vl_polymarket_watchlist.data.orderbooks import repository


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
