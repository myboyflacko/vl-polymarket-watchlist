from void_liquidity.pipeline.markets import (
    POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED,
    POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED,
)


def test_whale_qualified_markets_pipeline_event_contract() -> None:
    assert (
        POLYMARKET_WHALE_QUALIFIED_MARKETS_REQUESTED
        == "pipeline.markets.qualified.requested"
    )
    assert (
        POLYMARKET_WHALE_QUALIFIED_MARKETS_STARTED
        == "pipeline.markets.qualified.started"
    )
    assert (
        POLYMARKET_WHALE_QUALIFIED_MARKETS_COMPLETED
        == "pipeline.markets.qualified.completed"
    )
    assert (
        POLYMARKET_WHALE_QUALIFIED_MARKETS_FAILED
        == "pipeline.markets.qualified.failed"
    )
