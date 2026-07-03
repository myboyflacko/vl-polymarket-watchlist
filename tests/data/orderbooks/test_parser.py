from datetime import UTC, datetime
from decimal import Decimal

from vl_polymarket_watchlist.data.orderbooks.parser import parse_orderbook_payload


NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_orderbook_parser_uses_max_bid_and_min_ask() -> None:
    result = parse_orderbook_payload(
        condition_id="condition-1",
        token_id="token-1",
        generated_at=NOW,
        payload={
            "timestamp": "1780272000",
            "hash": "book-hash",
            "bids": [
                {"price": "0.40", "size": "100"},
                {"price": "0.45", "size": "50"},
            ],
            "asks": [
                {"price": "0.55", "size": "20"},
                {"price": "0.50", "size": "30"},
            ],
            "min_order_size": "1",
            "tick_size": "0.01",
            "neg_risk": False,
            "last_trade_price": "0.47",
        },
    )

    assert result.best_bid == Decimal("0.45")
    assert result.best_ask == Decimal("0.50")
    assert result.spread == Decimal("0.05")
    assert result.midpoint == Decimal("0.475")
    assert result.bid_depth_top_1 == Decimal("100")
    assert result.ask_depth_top_1 == Decimal("20")
    assert result.valid_orderbook is True


def test_orderbook_parser_marks_crossed_book_invalid() -> None:
    result = parse_orderbook_payload(
        condition_id="condition-1",
        token_id="token-1",
        generated_at=NOW,
        payload={
            "bids": [{"price": "0.60", "size": "100"}],
            "asks": [{"price": "0.50", "size": "30"}],
        },
    )

    assert result.valid_orderbook is False
    assert result.invalid_reason == "crossed_orderbook"
