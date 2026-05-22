import pytest
from pydantic import ValidationError

from void_liquidity.adapters.polymarket.api.params import ActivityParams


WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
MARKET = "0x" + "b" * 64


def test_activity_params_output_serializes_lists() -> None:
    params = ActivityParams(
        user=WALLET,
        market=[MARKET],
        type=["trade"],
        side="buy",
        sortBy="timestamp",
        sortDirection="desc",
    )

    assert params.output_params()["market"] == MARKET
    assert params.output_params()["type"] == "TRADE"
    assert params.output_params()["side"] == "BUY"
    assert params.output_params()["sortBy"] == "TIMESTAMP"


def test_activity_params_rejects_market_and_event_id_together() -> None:
    with pytest.raises(ValidationError):
        ActivityParams(
            user=WALLET,
            market=[MARKET],
            eventId=[1],
        )


def test_activity_params_rejects_offset_above_polymarket_limit() -> None:
    with pytest.raises(ValidationError):
        ActivityParams(user=WALLET, offset=3500)
