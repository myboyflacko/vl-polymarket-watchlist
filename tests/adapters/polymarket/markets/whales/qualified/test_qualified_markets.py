from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.candidates.repository import (
    persist_market_candidates,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.models import (
    WhaleDiscoveryRun,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.models import (
    WhaleSelectionRun,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified import (
    service as qualified_module,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    WhaleQualifiedMarketProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.service import (
    WhaleQualifiedMarketService,
    list_qualified_markets,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.models import (
    QualifiedMarketRun,
)
from void_liquidity.data.base import Base
from void_liquidity.data.engine import create_database_engine, database_session
from void_liquidity.settings import get_settings


NOW = datetime(2026, 5, 31, tzinfo=UTC)


def test_list_qualified_markets_filters_confirmed_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        qualified_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="confirmed", weighted_avg_price=0.4, cur_price=0.5),
            _candidate(token_id="pain", weighted_avg_price=0.6, cur_price=0.5),
        ],
    )

    result = list_qualified_markets(WhaleQualifiedMarketProfile(name="confirmed"))

    assert [market.candidate.token_id for market in result.qualified_markets] == [
        "confirmed"
    ]
    assert result.qualified_markets[0].price_delta == 0.09999999999999998
    assert result.qualified_markets[0].value_per_wallet == 10


def test_list_qualified_markets_filters_pain_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        qualified_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="confirmed", weighted_avg_price=0.4, cur_price=0.5),
            _candidate(token_id="pain", weighted_avg_price=0.6, cur_price=0.5),
        ],
    )

    result = list_qualified_markets(WhaleQualifiedMarketProfile(name="pain"))

    assert [market.candidate.token_id for market in result.qualified_markets] == [
        "pain"
    ]
    assert result.qualified_markets[0].score == 0.9999999999999998


def test_list_qualified_markets_ranks_high_value_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        qualified_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="small", total_current_value=15),
            _candidate(token_id="large", total_current_value=90),
        ],
    )

    result = list_qualified_markets(
        WhaleQualifiedMarketProfile(name="high_value", min_total_current_value=20),
    )

    assert [market.candidate.token_id for market in result.qualified_markets] == [
        "large"
    ]
    assert result.qualified_markets[0].score == 90


def test_list_qualified_markets_ranks_value_per_wallet_and_applies_limit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        qualified_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="dense", whale_count=3, total_current_value=90),
            _candidate(token_id="wide", whale_count=9, total_current_value=180),
        ],
    )

    result = list_qualified_markets(
        WhaleQualifiedMarketProfile(name="value_per_wallet"),
        limit=1,
    )

    assert [market.candidate.token_id for market in result.qualified_markets] == [
        "dense"
    ]
    assert result.qualified_markets[0].score == 30


def test_whale_qualified_market_service_persists_run_linked_to_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    _insert_parent_runs(database_path)
    persist_market_candidates(
        [_candidate(token_id="token-1", total_current_value=90)],
        run_id="candidate-run-1",
        selection_run_id="selection-run-1",
        min_whale_count=3,
        position_count=3,
        error_count=0,
        seen_at=NOW,
    )
    service = WhaleQualifiedMarketService(
        profile=WhaleQualifiedMarketProfile(name="high_value"),
    )

    result = service.run(candidate_run_id="candidate-run-1")
    service.persist(
        result=result,
        run_id="qualified-run-1",
        candidate_run_id="candidate-run-1",
        generated_at=NOW,
    )
    persisted = service.list(run_id="qualified-run-1")

    with database_session(database_path) as session:
        run = session.scalar(select(QualifiedMarketRun))

    assert run is not None
    assert run.candidate_run_id == "candidate-run-1"
    assert run.qualified_market_count == 1
    assert [market.candidate.token_id for market in persisted.qualified_markets] == [
        "token-1"
    ]


def _prepare_database(monkeypatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path


def _insert_parent_runs(database_path: Path) -> None:
    with database_session(database_path) as session:
        session.add(
            WhaleDiscoveryRun(
                run_id="discovery-run-1",
                profile_version="test",
                status="completed",
                started_at=NOW,
                finished_at=NOW,
                generated_at=NOW,
                candidate_wallet_count=3,
                checked_wallet_count=3,
                accepted_wallet_count=3,
                profile={},
            )
        )
        session.add(
            WhaleSelectionRun(
                run_id="selection-run-1",
                discovery_run_id="discovery-run-1",
                generated_at=NOW,
                profile={},
                ranking_method="test",
                selected_wallet_count=3,
                removed_wallet_count=0,
            )
        )
        session.commit()


def _candidate(
    *,
    token_id: str,
    whale_count: int = 3,
    total_current_value: float = 30,
    weighted_avg_price: float = 0.4,
    cur_price: float = 0.5,
) -> MarketCandidate:
    return MarketCandidate(
        token_id=token_id,
        condition_id="0x" + "1" * 64,
        title="Will this happen?",
        slug="will-this-happen",
        outcome="Yes",
        whale_count=whale_count,
        wallets=["wallet-1", "wallet-2", "wallet-3"],
        total_size=30,
        total_current_value=total_current_value,
        weighted_avg_price=weighted_avg_price,
        cur_price=cur_price,
        opposite_token_id="no-token",
        opposite_outcome="No",
        end_date=date(2026, 7, 20),
    )
