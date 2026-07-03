from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from vl_polymarket_watchlist.core.db.base import Base
from vl_polymarket_watchlist.core.db.models import (
    MarketDiscoveryObservation,
    MarketDiscoveryRun,
    PolymarketCondition,
    PolymarketToken,
)
from vl_polymarket_watchlist.markets import repository
from vl_polymarket_watchlist.markets.domain import (
    ConditionPayload,
    MarketObservation,
    TokenPayload,
)


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_persist_discovery_run_upserts_registry_and_appends_observations(
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

    stored_count = repository.persist_discovery_run(
        run_id="run-1",
        source="whale_discovery",
        source_version="v1",
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        generated_at=NOW,
        config_json={"source": "whale_discovery"},
        checked_count=1,
        observations=[
            _observation(token_id="token-1", title="Original"),
            _observation(token_id="token-1", title="Updated"),
        ],
        error_count=0,
    )

    with Session(engine) as session:
        run = session.get(MarketDiscoveryRun, "run-1")
        conditions = list(session.scalars(select(PolymarketCondition)))
        tokens = list(session.scalars(select(PolymarketToken)))
        observations = list(session.scalars(select(MarketDiscoveryObservation)))

    assert stored_count == 2
    assert run is not None
    assert run.observed_count == 2
    assert len(conditions) == 1
    assert conditions[0].title == "Updated"
    assert len(tokens) == 1
    assert len(observations) == 2


def _observation(*, token_id: str, title: str) -> MarketObservation:
    condition = ConditionPayload(
        condition_id="condition-1",
        title=title,
        slug="slug",
        question=title,
        end_date=NOW,
        raw_latest_payload={"title": title},
    )
    token = TokenPayload(
        token_id=token_id,
        condition_id="condition-1",
        outcome="Yes",
        opposite_token_id="token-2",
        opposite_outcome="No",
    )
    return MarketObservation(
        source="whale_discovery",
        observed_at=NOW,
        condition=condition,
        token=token,
        raw_payload={"title": title},
    )
