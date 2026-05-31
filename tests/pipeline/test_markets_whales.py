from void_liquidity.pipeline.markets import (
    POLYMARKET_WHALE_MARKETS_COMPLETED,
    POLYMARKET_WHALE_MARKETS_FAILED,
    POLYMARKET_WHALE_MARKETS_REQUESTED,
    POLYMARKET_WHALE_MARKETS_STARTED,
)


def test_whale_markets_pipeline_event_contract() -> None:
    assert POLYMARKET_WHALE_MARKETS_REQUESTED == "pipeline.markets.requested"
    assert POLYMARKET_WHALE_MARKETS_STARTED == "pipeline.markets.started"
    assert POLYMARKET_WHALE_MARKETS_COMPLETED == "pipeline.markets.completed"
    assert POLYMARKET_WHALE_MARKETS_FAILED == "pipeline.markets.failed"
