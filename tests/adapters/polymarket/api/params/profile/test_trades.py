import pytest
from pydantic import ValidationError

from void_liquidity.adapters.polymarket.api.params import TradesParams


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
MARKET = "0x" + "b" * 64


def test_trades_params_output_serializes_lists_and_uppercases() -> None:
    params = TradesParams(
        user=WALLET,
        market=[MARKET],
        side="buy",
        filterType="cash",
        filterAmount=100,
    )

    assert params.output_params()["market"] == MARKET
    assert params.output_params()["side"] == "BUY"
    assert params.output_params()["filterType"] == "CASH"


def test_trades_params_rejects_market_and_event_id_together() -> None:
    with pytest.raises(ValidationError):
        TradesParams(user=WALLET, market=[MARKET], eventId=[1])


def test_trades_params_rejects_filter_type_without_amount() -> None:
    with pytest.raises(ValidationError):
        TradesParams(user=WALLET, filterType="cash")


def test_trades_params_rejects_offset_above_polymarket_limit() -> None:
    with pytest.raises(ValidationError):
        TradesParams(user=WALLET, offset=10_001)
