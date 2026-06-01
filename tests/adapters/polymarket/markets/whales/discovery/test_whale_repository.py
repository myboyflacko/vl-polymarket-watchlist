from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from void_liquidity.adapters.polymarket.markets.whales.discovery.models import (
    DiscoveredWhale,
    DiscoveredWhaleMetric,
    WhaleDiscoveryRun,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
    list_latest_discovered_whales,
    list_latest_discovered_whale_wallets,
    persist_whale_discovery_run,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.domain import (
    CollectionQuality,
    ExposureMetrics,
    LeaderboardMetrics,
    MarketMetrics,
    TradeMetrics,
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    Whales,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.data.base import Base
from void_liquidity.data.engine import create_database_engine, database_session
from void_liquidity.settings import get_settings


NOW = datetime(2026, 5, 28, tzinfo=UTC)
LATER = datetime(2026, 5, 29, tzinfo=UTC)


def test_list_latest_discovered_whale_wallets_returns_empty_list(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    assert list_latest_discovered_whale_wallets() == []


def test_list_latest_discovered_whale_wallets_returns_latest_run_wallets_in_insert_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)

    with database_session(database_path) as session:
        session.add_all(
            [
                _discovery_run(run_id="run-1", generated_at=NOW),
                _discovery_run(run_id="run-2", generated_at=LATER),
            ]
        )
        session.add_all(
            [
                DiscoveredWhale(
                    id=1,
                    proxy_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    identity={},
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                ),
                DiscoveredWhale(
                    id=2,
                    proxy_wallet="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    identity={},
                    first_seen_at=LATER,
                    last_seen_at=LATER,
                ),
                DiscoveredWhale(
                    id=3,
                    proxy_wallet="0xcccccccccccccccccccccccccccccccccccccccc",
                    identity={},
                    first_seen_at=LATER,
                    last_seen_at=LATER,
                ),
            ]
        )
        session.add_all(
            [
                DiscoveredWhaleMetric(
                    run_id="run-1",
                    identity_id=1,
                    metrics=_whale_metrics(100),
                    collection_quality={},
                    generated_at=NOW,
                ),
                DiscoveredWhaleMetric(
                    run_id="run-2",
                    identity_id=2,
                    metrics=_whale_metrics(200),
                    collection_quality={},
                    generated_at=LATER,
                ),
                DiscoveredWhaleMetric(
                    run_id="run-2",
                    identity_id=3,
                    metrics=_whale_metrics(300),
                    collection_quality={},
                    generated_at=LATER,
                ),
            ]
        )
        session.commit()

    assert list_latest_discovered_whale_wallets() == [
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "0xcccccccccccccccccccccccccccccccccccccccc",
    ]


def test_list_latest_discovered_whales_returns_empty_model_without_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)

    whales = list_latest_discovered_whales()

    assert whales.whales == []
    assert whales.candidate_wallet_count == 0
    assert whales.checked_wallet_count == 0


def test_list_latest_discovered_whales_reconstructs_latest_run_from_snapshots(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)
    earlier_whales = Whales(
        whales=[_whale("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", volume=100)],
        candidate_wallet_count=1,
        checked_wallet_count=1,
        generated_at=NOW,
        profile_version="test",
    )
    later_whales = Whales(
        whales=[
            _whale("0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", volume=200),
            _whale("0xcccccccccccccccccccccccccccccccccccccccc", volume=300),
        ],
        candidate_wallet_count=2,
        checked_wallet_count=2,
        generated_at=LATER,
        profile_version="test",
    )
    profile = WhaleDiscoveryProfile(wallet_count=2)

    persist_whale_discovery_run(
        profile=profile,
        run_id="run-1",
        started_at=NOW,
        finished_at=NOW,
        generated_at=NOW,
        whales=earlier_whales,
    )
    persist_whale_discovery_run(
        profile=profile,
        run_id="run-2",
        started_at=LATER,
        finished_at=LATER,
        generated_at=LATER,
        whales=later_whales,
    )

    whales = list_latest_discovered_whales()

    assert [whale.proxy_wallet for whale in whales.whales] == [
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "0xcccccccccccccccccccccccccccccccccccccccc",
    ]
    assert whales.candidate_wallet_count == 2
    assert whales.whales[1].metrics.trades.trade_volume_30d == 300


def test_persist_whale_discovery_dedupes_wallet_identity_and_appends_snapshots(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    profile = WhaleDiscoveryProfile(wallet_count=1)

    persist_whale_discovery_run(
        profile=profile,
        run_id="run-1",
        started_at=NOW,
        finished_at=NOW,
        generated_at=NOW,
        whales=Whales(
            whales=[_whale("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", volume=100)],
            candidate_wallet_count=1,
            checked_wallet_count=1,
            generated_at=NOW,
            profile_version="test",
        ),
    )
    persist_whale_discovery_run(
        profile=profile,
        run_id="run-2",
        started_at=LATER,
        finished_at=LATER,
        generated_at=LATER,
        whales=Whales(
            whales=[_whale("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", volume=200)],
            candidate_wallet_count=1,
            checked_wallet_count=1,
            generated_at=LATER,
            profile_version="test",
        ),
    )

    with database_session(database_path) as session:
        identities = session.scalars(select(DiscoveredWhale)).all()
        snapshots = session.scalars(
            select(DiscoveredWhaleMetric).order_by(DiscoveredWhaleMetric.run_id)
        ).all()

    assert len(identities) == 1
    assert identities[0].first_seen_at == _sqlite_datetime(NOW)
    assert identities[0].last_seen_at == _sqlite_datetime(LATER)
    assert [snapshot.run_id for snapshot in snapshots] == ["run-1", "run-2"]
    assert snapshots[1].metrics["trades"]["trade_volume_30d"] == 200


def _prepare_database(monkeypatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path


def _discovery_run(*, run_id: str, generated_at: datetime) -> WhaleDiscoveryRun:
    return WhaleDiscoveryRun(
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
    )


def _whale(proxy_wallet: str, *, volume: float) -> Whale:
    return Whale(
        identity=WhaleIdentity(proxy_wallet=proxy_wallet),
        metrics=WhaleMetrics(
            leaderboard=LeaderboardMetrics(
                leaderboard_pnl_month=volume,
                leaderboard_volume_month=volume,
                candidate_source="both",
            ),
            trades=TradeMetrics(trade_volume_30d=volume),
            markets=MarketMetrics(),
            exposure=ExposureMetrics(current_position_value=volume),
            collection_quality=CollectionQuality(),
        ),
    )


def _whale_metrics(volume: float) -> dict:
    return _whale("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", volume=volume).metrics.model_dump(
        mode="json"
    )


def _sqlite_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=None)
