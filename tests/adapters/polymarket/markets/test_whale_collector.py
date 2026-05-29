import asyncio
from datetime import date
from typing import Any

from void_liquidity.adapters.polymarket.markets.whales import collector as collector_module
from void_liquidity.adapters.polymarket.markets.whales.collector import (
    WhaleMarketCollector,
)
from void_liquidity.adapters.polymarket.markets.whales.domain import (
    MarketCandidate,
    WhaleMarketCandidates,
    WhalePosition,
)


WALLET_ONE = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_TWO = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
CONDITION_ID = "0x" + "1" * 64
YES_TOKEN = "111"
NO_TOKEN = "222"


class FakeDataClient:
    def __init__(self, get_current_positions) -> None:
        self._get_current_positions = get_current_positions

    async def get_current_positions(self, params: Any) -> list[dict[str, Any]]:
        return await self._get_current_positions(None, params)


def _patch_data_client(monkeypatch, get_current_positions) -> None:
    monkeypatch.setattr(
        collector_module,
        "get_polymarket_data_client",
        lambda: FakeDataClient(get_current_positions),
    )


def test_whale_market_collector_groups_positions_by_token_id() -> None:
    candidates = WhaleMarketCollector(min_whale_count=1)._build_market_candidates(
        [
            _whale_position(WALLET_ONE, token_id=YES_TOKEN, current_value=100, size=10),
            _whale_position(WALLET_TWO, token_id=YES_TOKEN, current_value=50, size=5),
            _whale_position(
                WALLET_ONE,
                token_id=NO_TOKEN,
                outcome="No",
                current_value=75,
                size=15,
            ),
        ],
    )

    assert [candidate.token_id for candidate in candidates] == [YES_TOKEN, NO_TOKEN]
    assert candidates[0].whale_count == 2
    assert candidates[0].wallets == [WALLET_ONE, WALLET_TWO]
    assert candidates[0].total_current_value == 150
    assert candidates[0].total_size == 15
    assert candidates[0].weighted_avg_price == 0.4
    assert candidates[0].end_date == date(2026, 7, 20)
    assert candidates[1].condition_id == CONDITION_ID
    assert candidates[1].outcome == "No"


def test_whale_market_collector_filters_below_min_whale_count() -> None:
    candidates = WhaleMarketCollector()._build_market_candidates(
        [
            _whale_position(WALLET_ONE, token_id=YES_TOKEN),
            _whale_position(WALLET_TWO, token_id=YES_TOKEN),
        ]
    )

    assert candidates == []


def test_whale_market_collector_returns_empty_result_without_wallets(
    monkeypatch,
) -> None:
    monkeypatch.setattr(collector_module, "list_tracked_whale_wallets", lambda: [])

    result = asyncio.run(WhaleMarketCollector(min_whale_count=1).run())

    assert result.candidates == []
    assert result.positions == []
    assert result.errors == []


def test_whale_market_collector_fetches_and_groups_open_positions(
    monkeypatch,
) -> None:
    calls = []

    async def fake_get_current_positions(client: Any, params: Any) -> list[dict[str, Any]]:
        calls.append((params.user, params.offset, params.sizeThreshold))
        if params.user == WALLET_ONE:
            return [_position(asset=YES_TOKEN, current_value=100, size=10)]

        return [_position(asset=YES_TOKEN, current_value=50, size=5)]

    monkeypatch.setattr(
        collector_module,
        "list_tracked_whale_wallets",
        lambda: [WALLET_ONE, WALLET_TWO],
    )
    _patch_data_client(monkeypatch, fake_get_current_positions)

    result = asyncio.run(WhaleMarketCollector(min_whale_count=1).run())

    assert [(user, offset) for user, offset, _ in calls] == [
        (WALLET_ONE, 0),
        (WALLET_TWO, 0),
    ]
    assert {threshold for _, _, threshold in calls} == {1}
    assert len(result.positions) == 2
    assert len(result.candidates) == 1
    assert result.candidates[0].token_id == YES_TOKEN
    assert result.candidates[0].whale_count == 2
    assert result.errors == []


def test_whale_market_collector_keeps_processing_after_wallet_error(
    monkeypatch,
) -> None:
    async def fake_get_current_positions(client: Any, params: Any) -> list[dict[str, Any]]:
        if params.user == WALLET_ONE:
            raise RuntimeError("boom")

        return [_position(asset=YES_TOKEN, current_value=50)]

    monkeypatch.setattr(
        collector_module,
        "list_tracked_whale_wallets",
        lambda: [WALLET_ONE, WALLET_TWO],
    )
    _patch_data_client(monkeypatch, fake_get_current_positions)

    result = asyncio.run(WhaleMarketCollector(min_whale_count=1).run())

    assert len(result.positions) == 1
    assert len(result.candidates) == 1
    assert len(result.errors) == 1
    assert result.errors[0].proxy_wallet == WALLET_ONE
    assert result.errors[0].message == "boom"


def test_whale_market_collector_paginates_positions(
    monkeypatch,
) -> None:
    calls = []

    async def fake_get_current_positions(client: Any, params: Any) -> list[dict[str, Any]]:
        calls.append(params.offset)
        if params.offset == 0:
            return [
                _position(asset="1"),
                _position(asset="2"),
            ]

        return [_position(asset="3")]

    monkeypatch.setattr(collector_module, "list_tracked_whale_wallets", lambda: [WALLET_ONE])
    monkeypatch.setattr(collector_module, "POSITION_PAGE_LIMIT", 2)
    _patch_data_client(monkeypatch, fake_get_current_positions)

    result = asyncio.run(WhaleMarketCollector(min_whale_count=1).run())

    assert calls == [0, 2]
    assert [position.token_id for position in result.positions] == ["1", "2", "3"]
    assert len(result.candidates) == 3


def test_whale_market_collector_persists_candidates(monkeypatch) -> None:
    persisted: list[dict] = []

    def fake_persist_market_candidates(candidates, **kwargs) -> None:
        persisted.append({"candidates": candidates, **kwargs})

    monkeypatch.setattr(
        collector_module,
        "persist_market_candidates",
        fake_persist_market_candidates,
    )
    result = _collector_result()

    WhaleMarketCollector(min_whale_count=2).persist(
        candidates=result,
        run_id="run-1",
    )

    assert persisted
    assert persisted[0]["candidates"] == result.candidates
    assert persisted[0]["run_id"] == "run-1"
    assert persisted[0]["min_whale_count"] == 2
    assert persisted[0]["position_count"] == 2
    assert persisted[0]["error_count"] == 0


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


def _position(
    *,
    asset: str,
    current_value: float = 100,
    size: float = 10,
) -> dict[str, Any]:
    return {
        "asset": asset,
        "conditionId": CONDITION_ID,
        "outcome": "Yes",
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


def _collector_result() -> WhaleMarketCandidates:
    return WhaleMarketCandidates(
        candidates=[
            MarketCandidate(
                token_id=YES_TOKEN,
                condition_id=CONDITION_ID,
                title="Will this happen?",
                slug="will-this-happen",
                outcome="Yes",
                whale_count=2,
                wallets=[WALLET_ONE, WALLET_TWO],
                total_size=20,
                total_current_value=200,
                weighted_avg_price=0.4,
                cur_price=0.5,
            ),
        ],
        positions=[
            _whale_position(WALLET_ONE, token_id=YES_TOKEN),
            _whale_position(WALLET_TWO, token_id=YES_TOKEN),
        ],
    )
