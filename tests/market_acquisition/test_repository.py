from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from vl_polymarket_watchlist.core.db.base import Base
from vl_polymarket_watchlist.market_acquisition.domain import Market
from vl_polymarket_watchlist.market_acquisition.models import (
    CollectorRun,
    CollectorRunMarket,
    Market as MarketRow,
)
from vl_polymarket_watchlist.market_acquisition import repository


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_persist_collector_run_deduplicates_markets_and_links_run(
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

    stored_count = repository.persist_collector_run(
        run_id="run-1",
        strategy_name="leaderboard_current_positions",
        strategy_params={"name": "leaderboard_current_positions"},
        generated_at=NOW,
        checked_market_count=2,
        markets=[
            _market(token_id="token-1", title="Original"),
            _market(token_id="token-1", title="Updated"),
        ],
    )

    with Session(engine) as session:
        run = session.get(CollectorRun, "run-1")
        markets = list(session.scalars(select(MarketRow)))
        links = list(session.scalars(select(CollectorRunMarket)))

    assert stored_count == 1
    assert run is not None
    assert run.stored_market_count == 1
    assert len(markets) == 1
    assert markets[0].title == "Updated"
    assert len(links) == 1


def _market(*, token_id: str, title: str) -> Market:
    return Market(
        token_id=token_id,
        condition_id="condition-1",
        title=title,
        slug="slug",
        outcome="Yes",
        opposite_token_id="token-2",
        opposite_outcome="No",
    )
