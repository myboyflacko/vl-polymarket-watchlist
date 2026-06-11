import asyncio
import os
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

from whale_tracker.core.db.base import Base
from whale_tracker.core.db.engine import create_database_engine, database_session
from whale_tracker.settings import get_settings
from whale_tracker.tracker.markets import service as service_module
from whale_tracker.tracker.markets.domain import Market, WhalePosition
from whale_tracker.tracker.markets.filter import (
    TrackedMarketFilterProfile,
    build_market_candidates,
)
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    MarketObservation,
    MarketRun,
)
from whale_tracker.tracker.markets.repository import _batches
from whale_tracker.tracker.markets.service import MarketTrackerService
from whale_tracker.tracker.whales.models import (
    PolymarketWhale,
    WhaleObservation,
    WhaleRun,
)


NOW = datetime(2026, 6, 1, tzinfo=UTC)
WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
WALLET_THREE = "0xcccccccccccccccccccccccccccccccccccccccc"
CONDITION_ID = "0x" + "1" * 64
YES_TOKEN = "111"
NO_TOKEN = "222"


class FakeDataClient:
    async def get_current_positions(self, params: Any) -> list[dict[str, Any]]:
        if params.user == WALLET_ONE:
            return [_position(asset=YES_TOKEN, current_value=100, size=10)]

        if params.user == WALLET_THREE:
            return [_position(asset=YES_TOKEN, current_value=75, size=7.5)]

        return [
            _position(asset=YES_TOKEN, current_value=50, size=5),
            _position(asset=NO_TOKEN, outcome="No", current_value=25, size=5),
        ]


def test_build_market_candidates_groups_positions_by_token() -> None:
    candidates = build_market_candidates(
        [
            _whale_position(WALLET_ONE, token_id=YES_TOKEN, current_value=100, size=10),
            _whale_position(WALLET_TWO, token_id=YES_TOKEN, current_value=50, size=5),
            _whale_position(WALLET_ONE, token_id=NO_TOKEN, current_value=75, size=15),
        ],
    )

    assert [candidate.token_id for candidate in candidates] == [YES_TOKEN, NO_TOKEN]
    assert candidates[0].whale_count == 2
    assert candidates[0].wallets == [WALLET_ONE, WALLET_TWO]
    assert candidates[0].total_current_value == 150
    assert candidates[0].weighted_avg_price == 0.4


def test_batches_splits_large_payloads() -> None:
    assert _batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_tracked_market_filter_keeps_unique_condition_one_direction() -> None:
    result = TrackedMarketFilterProfile().run(
        [
            _market(
                token_id=YES_TOKEN,
                whale_count=5,
                total_current_value=300,
            ),
            _market(
                token_id=NO_TOKEN,
                wallets=["0x6"],
                whale_count=1,
                total_current_value=200,
            ),
        ]
    )

    assert [market.token_id for market in result] == [YES_TOKEN]


def test_tracked_market_filter_rejects_under_min_whale_count() -> None:
    result = TrackedMarketFilterProfile().run(
        [
            _market(
                token_id=YES_TOKEN,
                wallets=["0x1", "0x2", "0x3", "0x4"],
                whale_count=4,
                total_current_value=300,
            ),
        ]
    )

    assert result == []


def test_tracked_market_filter_accepts_five_of_six_whales() -> None:
    result = TrackedMarketFilterProfile().run(
        [
            _market(
                token_id=YES_TOKEN,
                wallets=["0x1", "0x2", "0x3", "0x4", "0x5"],
                whale_count=5,
            ),
            _market(
                token_id=NO_TOKEN,
                wallets=["0x6"],
                whale_count=1,
            ),
        ]
    )

    assert [market.token_id for market in result] == [YES_TOKEN]


def test_tracked_market_filter_rejects_five_of_seven_whales() -> None:
    result = TrackedMarketFilterProfile().run(
        [
            _market(
                token_id=YES_TOKEN,
                wallets=["0x1", "0x2", "0x3", "0x4", "0x5"],
                whale_count=5,
            ),
            _market(
                token_id=NO_TOKEN,
                wallets=["0x6", "0x7"],
                whale_count=2,
            ),
        ]
    )

    assert result == []


def test_market_tracker_run_persists_only_tracked_markets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_database(monkeypatch)
    _insert_whale_observation_runs(database_url)
    monkeypatch.setattr(
        service_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(),
    )
    service = MarketTrackerService(
        filter_profile=TrackedMarketFilterProfile(min_whale_count=3),
    )

    result = asyncio.run(service.run(whales_run_id="whales-run-1", now=NOW))

    assert result.run_id.endswith("-markets")
    assert [market.token_id for market in result.markets] == [YES_TOKEN]

    with database_session(database_url) as session:
        run = session.scalar(select(MarketRun))
        identities = list(session.scalars(select(MarketIdentity)))
        observations = list(session.scalars(select(MarketObservation)))

    assert run is not None
    assert run.whales_run_id == "whales-run-1"
    assert run.checked_market_count == 2
    assert {identity.token_id for identity in identities} == {YES_TOKEN, NO_TOKEN}
    assert len(observations) == 4
    assert sum(
        observation.current_value
        for observation in observations
        if observation.market.token_id == YES_TOKEN
    ) == 225


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


def _insert_whale_observation_runs(database_url: str) -> None:
    with database_session(database_url) as session:
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
        three = PolymarketWhale(
            proxy_wallet=WALLET_THREE,
            identity={"proxy_wallet": WALLET_THREE},
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        session.add_all([one, two, three])
        session.flush()

        whales = [one, two, three]
        for index in range(3):
            generated_at = NOW.replace(hour=NOW.hour + index)
            run_id = f"whales-run-{index + 1}"
            session.add(
                WhaleRun(
                    run_id=run_id,
                    status="completed",
                    profile_version="test",
                    started_at=generated_at,
                    finished_at=generated_at,
                    generated_at=generated_at,
                    checked_wallet_count=len(whales),
                    observed_wallet_count=len(whales),
                )
            )
            session.flush()
            session.add_all(
                [
                    WhaleObservation(
                        run_id=run_id,
                        whale_id=whale.id,
                        metrics={"candidate_source": "both"},
                        generated_at=generated_at,
                    )
                    for whale in whales
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
    wallets: list[str] | None = None,
    weighted_avg_price: float = 0.4,
    cur_price: float = 0.5,
    total_current_value: float = 30,
    whale_count: int = 3,
) -> Market:
    actual_wallets = wallets or [f"0x{index}" for index in range(1, whale_count + 1)]
    return Market(
        token_id=token_id,
        condition_id=CONDITION_ID,
        title="Will this happen?",
        slug="will-this-happen",
        outcome="Yes",
        whale_count=whale_count,
        wallets=actual_wallets,
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
