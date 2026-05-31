from datetime import date

from void_liquidity.adapters.polymarket.markets.whales.domain import MarketCandidate
from void_liquidity.adapters.polymarket.signals.whales import signals as signals_module
from void_liquidity.adapters.polymarket.signals.whales.domain import MarketSignalProfile
from void_liquidity.adapters.polymarket.signals.whales.signals import (
    list_market_signals,
)


def test_list_market_signals_filters_confirmed_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        signals_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="confirmed", weighted_avg_price=0.4, cur_price=0.5),
            _candidate(token_id="pain", weighted_avg_price=0.6, cur_price=0.5),
        ],
    )

    result = list_market_signals(MarketSignalProfile(name="confirmed"))

    assert [signal.candidate.token_id for signal in result.signals] == ["confirmed"]
    assert result.signals[0].price_delta == 0.09999999999999998
    assert result.signals[0].value_per_wallet == 10


def test_list_market_signals_filters_pain_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        signals_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="confirmed", weighted_avg_price=0.4, cur_price=0.5),
            _candidate(token_id="pain", weighted_avg_price=0.6, cur_price=0.5),
        ],
    )

    result = list_market_signals(MarketSignalProfile(name="pain"))

    assert [signal.candidate.token_id for signal in result.signals] == ["pain"]
    assert result.signals[0].score == 0.9999999999999998


def test_list_market_signals_ranks_high_value_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        signals_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="small", total_current_value=15),
            _candidate(token_id="large", total_current_value=90),
        ],
    )

    result = list_market_signals(
        MarketSignalProfile(name="high_value", min_total_current_value=20),
    )

    assert [signal.candidate.token_id for signal in result.signals] == ["large"]
    assert result.signals[0].score == 90


def test_list_market_signals_ranks_value_per_wallet_and_applies_limit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        signals_module,
        "list_latest_market_candidates",
        lambda: [
            _candidate(token_id="dense", whale_count=3, total_current_value=90),
            _candidate(token_id="wide", whale_count=9, total_current_value=180),
        ],
    )

    result = list_market_signals(
        MarketSignalProfile(name="value_per_wallet"),
        limit=1,
    )

    assert [signal.candidate.token_id for signal in result.signals] == ["dense"]
    assert result.signals[0].score == 30


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
