import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from void_liquidity.adapters.polymarket.discovery.whales.models import (
    TrackedWhale,
    TrackedWhaleMetricSnapshot,
    WhaleTrackerRun,
)
from void_liquidity.adapters.polymarket.discovery.whales_v2.profiles import (
    WhaleTrackerV2Profile,
)
from void_liquidity.adapters.polymarket.discovery.whales_v2.tracker import (
    WhaleTrackerV2,
)
from void_liquidity.adapters.polymarket.discovery.whales_v2 import (
    tracker as tracker_module,
)
from void_liquidity.adapters.polymarket.ranking import rank_trade_first_whales
from void_liquidity.data import Base, create_database_engine, database_session
from void_liquidity.settings import get_settings


WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
MARKET_ONE = "0x" + "1" * 64
NOW = datetime(2026, 5, 26, tzinfo=UTC)


class FakeDataClient:
    def __init__(
        self,
        *,
        get_leaderboard=None,
        get_trades=None,
        get_current_positions=None,
    ) -> None:
        self._get_leaderboard = get_leaderboard or _empty_page
        self._get_trades = get_trades or _empty_page
        self._get_current_positions = get_current_positions or _empty_page

    async def get_leaderboard(self, params: Any) -> list[dict[str, Any]]:
        return await self._get_leaderboard(None, params)

    async def get_trades(self, params: Any) -> list[dict[str, Any]]:
        return await self._get_trades(None, params)

    async def get_current_positions(self, params: Any) -> list[dict[str, Any]]:
        return await self._get_current_positions(None, params)


async def _empty_page(client: Any, params: Any) -> list[dict[str, Any]]:
    return []


def _patch_data_client(
    monkeypatch,
    *,
    get_leaderboard=None,
    get_trades=None,
    get_current_positions=None,
) -> None:
    monkeypatch.setattr(
        tracker_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(
            get_leaderboard=get_leaderboard,
            get_trades=get_trades,
            get_current_positions=get_current_positions,
        ),
    )


def _profile() -> WhaleTrackerV2Profile:
    return WhaleTrackerV2Profile(
        wallet_count=2,
        wallet_batch_size=2,
        leaderboard_limit=2,
        trade_limit=2,
        max_trade_pages_per_wallet=3,
    )


def _trade(
    *,
    days_ago: int,
    side: str,
    price: float,
    size: float,
    market: str = MARKET_ONE,
) -> dict[str, Any]:
    return {
        "timestamp": int((NOW - timedelta(days=days_ago)).timestamp()),
        "side": side,
        "price": price,
        "size": size,
        "conditionId": market,
    }


def test_whale_tracker_v2_collects_trade_first_metrics(
    monkeypatch,
) -> None:
    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        if params.orderBy == "PNL":
            return [
                {
                    "proxyWallet": WALLET_ONE,
                    "rank": 1,
                    "pnl": 100,
                    "userName": "wallet one",
                },
                {"proxyWallet": WALLET_TWO, "rank": 2, "pnl": 50},
            ]

        return [
            {"proxyWallet": WALLET_ONE, "rank": 5, "vol": 10_000},
            {"proxyWallet": WALLET_TWO, "rank": 6, "vol": 5_000},
        ]

    async def fake_get_trades(client: Any, params: Any) -> list[dict[str, Any]]:
        if params.user == WALLET_ONE and params.offset == 0:
            return [
                _trade(days_ago=1, side="BUY", price=0.5, size=100),
                _trade(days_ago=2, side="SELL", price=0.6, size=20),
            ]

        if params.user == WALLET_ONE:
            return [_trade(days_ago=40, side="BUY", price=0.5, size=1)]

        return [_trade(days_ago=1, side="BUY", price=0.25, size=40)]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        assert params.market == [MARKET_ONE]
        return [{"currentValue": 250}]

    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
        get_trades=fake_get_trades,
        get_current_positions=fake_get_current_positions,
    )

    result = asyncio.run(WhaleTrackerV2(profile=_profile()).run(now=NOW))
    whale = result.whales[0]

    assert result.candidate_wallet_count == 2
    assert whale.proxy_wallet == WALLET_ONE
    assert whale.condition_ids_30d == [MARKET_ONE]
    assert whale.metrics.leaderboard.leaderboard_pnl_month == 100
    assert whale.metrics.leaderboard.leaderboard_volume_month == 10_000
    assert whale.metrics.trades.trade_count_30d == 2
    assert whale.metrics.trades.trade_volume_30d == 62
    assert whale.metrics.trades.buy_volume_30d == 50
    assert whale.metrics.trades.sell_volume_30d == 12
    assert whale.metrics.trades.net_flow_30d == 38
    assert whale.metrics.trades.net_flow_ratio_30d == 38 / 62
    assert whale.metrics.markets.unique_markets_30d == 1
    assert whale.metrics.exposure.current_position_value == 250


def test_whale_tracker_v2_isolates_trade_errors_per_wallet(monkeypatch) -> None:
    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        return [
            {"proxyWallet": WALLET_ONE, "rank": 1, "pnl": 100, "vol": 10_000},
            {"proxyWallet": WALLET_TWO, "rank": 2, "pnl": 50, "vol": 5_000},
        ]

    async def fake_get_trades(client: Any, params: Any) -> list[dict[str, Any]]:
        if params.user == WALLET_TWO:
            raise RuntimeError("wallet trade api down")

        return [_trade(days_ago=1, side="BUY", price=0.5, size=100)]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        return [{"currentValue": 250}]

    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
        get_trades=fake_get_trades,
        get_current_positions=fake_get_current_positions,
    )

    result = asyncio.run(WhaleTrackerV2(profile=_profile()).run(now=NOW))

    assert result.successful_wallet_count == 1
    assert result.failed_wallet_count == 1
    assert result.partial is True
    assert result.collection_errors[0].proxy_wallet == WALLET_TWO
    assert result.collection_errors[0].stage == "trades"
    assert result.collection_errors[0].error == "wallet trade api down"


def test_whale_tracker_v2_isolates_current_position_errors_per_wallet(
    monkeypatch,
) -> None:
    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        return [
            {"proxyWallet": WALLET_ONE, "rank": 1, "pnl": 100, "vol": 10_000},
            {"proxyWallet": WALLET_TWO, "rank": 2, "pnl": 50, "vol": 5_000},
        ]

    async def fake_get_trades(client: Any, params: Any) -> list[dict[str, Any]]:
        return [_trade(days_ago=1, side="BUY", price=0.5, size=100)]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        if params.user == WALLET_TWO:
            raise RuntimeError("position api down")

        return [{"currentValue": 250}]

    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
        get_trades=fake_get_trades,
        get_current_positions=fake_get_current_positions,
    )

    result = asyncio.run(WhaleTrackerV2(profile=_profile()).run(now=NOW))

    assert result.successful_wallet_count == 1
    assert result.failed_wallet_count == 1
    assert result.collection_errors[0].proxy_wallet == WALLET_TWO
    assert result.collection_errors[0].stage == "current_positions"


def test_whale_tracker_v2_leaderboard_errors_remain_fatal(monkeypatch) -> None:
    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        raise RuntimeError("leaderboard down")

    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
    )

    try:
        asyncio.run(WhaleTrackerV2(profile=_profile()).run(now=NOW))
    except RuntimeError as exc:
        assert str(exc) == "leaderboard down"
    else:
        raise AssertionError("expected leaderboard error")


def test_whale_tracker_v2_stops_descending_trade_pagination_at_window(
    monkeypatch,
) -> None:
    trade_offsets: list[int] = []

    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        return [{"proxyWallet": WALLET_ONE, "rank": 1, "pnl": 100, "vol": 10_000}]

    async def fake_get_trades(client: Any, params: Any) -> list[dict[str, Any]]:
        trade_offsets.append(params.offset)

        if params.offset == 0:
            return [_trade(days_ago=1, side="BUY", price=0.5, size=100)]

        return [
            _trade(days_ago=40, side="BUY", price=0.5, size=1),
            _trade(days_ago=41, side="BUY", price=0.5, size=1),
        ]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        return []

    profile = WhaleTrackerV2Profile(
        wallet_count=1,
        trade_limit=1,
        max_trade_pages_per_wallet=10,
    )
    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
        get_trades=fake_get_trades,
        get_current_positions=fake_get_current_positions,
    )

    result = asyncio.run(WhaleTrackerV2(profile=profile).run(now=NOW))

    assert trade_offsets == [0, 1]
    assert result.whales[0].metrics.collection_quality.trades_complete is True


def test_whale_tracker_v2_marks_unsorted_trade_pages_incomplete(monkeypatch) -> None:
    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        return [{"proxyWallet": WALLET_ONE, "rank": 1, "pnl": 100, "vol": 100}]

    async def fake_get_trades(client: Any, params: Any) -> list[dict[str, Any]]:
        return [
            _trade(days_ago=3, side="BUY", price=0.5, size=10),
            _trade(days_ago=1, side="BUY", price=0.5, size=10),
        ]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        return []

    profile = WhaleTrackerV2Profile(
        wallet_count=1,
        trade_limit=2,
        max_trade_pages_per_wallet=1,
    )
    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
        get_trades=fake_get_trades,
        get_current_positions=fake_get_current_positions,
    )

    result = asyncio.run(WhaleTrackerV2(profile=profile).run(now=NOW))
    quality = result.whales[0].metrics.collection_quality

    assert quality.trades_sort_order == "unknown"
    assert quality.trades_complete is False


def test_whale_tracker_v2_persists_metric_snapshots(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    whales = asyncio.run(_build_persistable_whales(monkeypatch))

    WhaleTrackerV2(profile=_profile()).persist(
        whales=whales,
        run_id="run-v2",
        started_at=NOW,
        finished_at=NOW,
        ranking_result=rank_trade_first_whales(whales),
    )

    with database_session(database_path) as session:
        run = session.scalar(select(WhaleTrackerRun))
        tracked_whale = session.scalar(select(TrackedWhale))
        snapshot = session.scalar(select(TrackedWhaleMetricSnapshot))

    assert run is not None
    assert run.run_id == "run-v2"
    assert tracked_whale is not None
    assert tracked_whale.proxy_wallet == WALLET_ONE
    assert snapshot is not None
    assert snapshot.proxy_wallet == WALLET_ONE
    assert snapshot.metrics["trades"]["net_flow_30d"] == 38
    assert snapshot.metrics["ranking"]["method"] == "trade_first_percentile_v1"
    assert snapshot.metrics["ranking"]["rank"] == 1


def test_whale_tracker_v2_persists_only_ranked_whales_as_tracked_whales(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "whales.sqlite3"
    monkeypatch.setenv("VOID_LIQUIDITY_SQLITE_PATH", str(database_path))
    get_settings.cache_clear()
    engine = create_database_engine(database_path)
    Base.metadata.create_all(engine)
    whales = asyncio.run(_build_two_persistable_whales(monkeypatch))
    ranking = rank_trade_first_whales(whales)

    WhaleTrackerV2(profile=_profile()).persist(
        whales=whales,
        run_id="run-v2-kept",
        started_at=NOW,
        finished_at=NOW,
        ranking_result=ranking,
    )

    with database_session(database_path) as session:
        tracked_whales = session.scalars(select(TrackedWhale)).all()
        snapshots = session.scalars(select(TrackedWhaleMetricSnapshot)).all()
        run = session.scalar(select(WhaleTrackerRun))

    assert run is not None
    assert run.accepted_wallet_count == len(ranking.ranked_whales)
    assert [whale.proxy_wallet for whale in tracked_whales] == [
        ranking.ranked_whales[0].whale.proxy_wallet
    ]
    assert len(snapshots) == 2
    removed_snapshot = next(
        snapshot
        for snapshot in snapshots
        if snapshot.proxy_wallet == ranking.removed_wallets[0]
    )
    assert removed_snapshot.metrics["ranking"]["removed"] is True


async def _build_persistable_whales(monkeypatch) -> Any:
    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        return [{"proxyWallet": WALLET_ONE, "rank": 1, "pnl": 100, "vol": 10_000}]

    async def fake_get_trades(client: Any, params: Any) -> list[dict[str, Any]]:
        if params.offset > 0:
            return []

        return [
            _trade(days_ago=1, side="BUY", price=0.5, size=100),
            _trade(days_ago=2, side="SELL", price=0.6, size=20),
        ]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        return [{"currentValue": 250}]

    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
        get_trades=fake_get_trades,
        get_current_positions=fake_get_current_positions,
    )
    return await WhaleTrackerV2(profile=WhaleTrackerV2Profile(wallet_count=1)).run(
        now=NOW
    )


async def _build_two_persistable_whales(monkeypatch) -> Any:
    async def fake_get_leaderboard(client: Any, params: Any) -> list[dict[str, Any]]:
        return [
            {"proxyWallet": WALLET_ONE, "rank": 1, "pnl": 100, "vol": 10_000},
            {"proxyWallet": WALLET_TWO, "rank": 2, "pnl": 10, "vol": 1_000},
        ]

    async def fake_get_trades(client: Any, params: Any) -> list[dict[str, Any]]:
        if params.offset > 0:
            return []

        if params.user == WALLET_ONE:
            return [_trade(days_ago=1, side="BUY", price=0.5, size=100)]

        return [_trade(days_ago=1, side="BUY", price=0.1, size=10)]

    async def fake_get_current_positions(
        client: Any,
        params: Any,
    ) -> list[dict[str, Any]]:
        return [{"currentValue": 250 if params.user == WALLET_ONE else 10}]

    _patch_data_client(
        monkeypatch,
        get_leaderboard=fake_get_leaderboard,
        get_trades=fake_get_trades,
        get_current_positions=fake_get_current_positions,
    )
    return await WhaleTrackerV2(profile=WhaleTrackerV2Profile(wallet_count=2)).run(
        now=NOW
    )
