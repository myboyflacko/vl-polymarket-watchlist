from datetime import UTC, datetime
from pathlib import Path

from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
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
from void_liquidity.adapters.polymarket.markets.whales.selection.profiles import (
    WhaleSelectionProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.selection import (
    service as selection_module,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.models import (
    WhaleSelectionRun,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.service import (
    WhaleSelectionService,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.repository import (
    list_selected_whales,
    list_selected_whale_wallets,
)
from void_liquidity.data.base import Base
from void_liquidity.data.engine import create_database_engine, database_session
from void_liquidity.settings import get_settings


NOW = datetime(2026, 5, 31, tzinfo=UTC)


def test_whale_selection_service_returns_empty_ranking_without_db_whales(
    monkeypatch,
) -> None:
    monkeypatch.setattr(selection_module, "get_latest_discovery_run_id", lambda: "run-1")
    monkeypatch.setattr(selection_module, "list_discovered_whales", lambda _: _whales([]))

    result = WhaleSelectionService().run()

    assert result.ranked_whales == []
    assert result.removed_whales == []


def test_whale_selection_service_ranks_latest_db_whales(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        selection_module,
        "get_latest_discovery_run_id",
        lambda: "run-1",
    )
    monkeypatch.setattr(
        selection_module,
        "list_discovered_whales",
        lambda _: _whales(
            [
                _whale("wallet-low", pnl=10, volume=10, exposure=10),
                _whale("wallet-high", pnl=100, volume=100, exposure=100),
            ]
        ),
    )

    result = WhaleSelectionService(
        profile=WhaleSelectionProfile(bottom_cut_percentile=0),
    ).run()

    assert [ranked.whale.proxy_wallet for ranked in result.ranked_whales] == [
        "wallet-high",
        "wallet-low",
    ]
    assert result.removed_whales == []


def test_whale_selection_service_returns_ranked_wallets(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        selection_module,
        "list_latest_selected_whale_wallets",
        lambda: ["wallet-high", "wallet-low"],
    )
    monkeypatch.setattr(
        selection_module,
        "get_latest_discovery_run_id",
        lambda: "run-1",
    )
    monkeypatch.setattr(
        selection_module,
        "list_discovered_whales",
        lambda _: _whales(
            [
                _whale("wallet-low", pnl=10, volume=10, exposure=10),
                _whale("wallet-high", pnl=100, volume=100, exposure=100),
            ]
        ),
    )

    wallets = WhaleSelectionService(
        profile=WhaleSelectionProfile(bottom_cut_percentile=0),
    ).list()

    assert wallets == ["wallet-high", "wallet-low"]


def test_whale_selection_service_persists_run_linked_to_discovery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = _prepare_database(monkeypatch, tmp_path)
    discovered = _whales(
        [
            _whale("wallet-low", pnl=10, volume=10, exposure=10),
            _whale("wallet-high", pnl=100, volume=100, exposure=100),
        ]
    )
    persist_whale_discovery_run(
        profile=WhaleDiscoveryProfile(wallet_count=2),
        run_id="discovery-run-1",
        started_at=NOW,
        finished_at=NOW,
        generated_at=NOW,
        whales=discovered,
    )
    service = WhaleSelectionService(
        profile=WhaleSelectionProfile(bottom_cut_percentile=0),
    )

    ranking = service.run(discovery_run_id="discovery-run-1")
    service.persist(
        ranking=ranking,
        run_id="selection-run-1",
        discovery_run_id="discovery-run-1",
        generated_at=NOW,
    )

    with database_session(database_path) as session:
        run = session.get(WhaleSelectionRun, "selection-run-1")

    assert run is not None
    assert run.discovery_run_id == "discovery-run-1"
    assert run.selected_wallet_count == 2
    assert list_selected_whale_wallets("selection-run-1") == [
        "wallet-high",
        "wallet-low",
    ]
    selected = list_selected_whales("selection-run-1")
    assert [whale.proxy_wallet for whale in selected.whales] == [
        "wallet-low",
        "wallet-high",
    ]


def _prepare_database(monkeypatch, tmp_path: Path) -> Path:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    return database_path


def _whales(whales: list[Whale]) -> Whales:
    return Whales(
        whales=whales,
        candidate_wallet_count=len(whales),
        checked_wallet_count=len(whales),
        generated_at=NOW,
        profile_version="test",
    )


def _whale(
    proxy_wallet: str,
    *,
    pnl: float,
    volume: float,
    exposure: float,
) -> Whale:
    return Whale(
        identity=WhaleIdentity(proxy_wallet=proxy_wallet),
        metrics=WhaleMetrics(
            leaderboard=LeaderboardMetrics(
                leaderboard_pnl_month=pnl,
                leaderboard_volume_month=volume,
                candidate_source="both",
            ),
            trades=TradeMetrics(trade_volume_30d=volume),
            markets=MarketMetrics(),
            exposure=ExposureMetrics(current_position_value=exposure),
            collection_quality=CollectionQuality(),
        ),
    )
