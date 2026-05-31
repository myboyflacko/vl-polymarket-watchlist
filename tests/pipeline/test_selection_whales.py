from void_liquidity.pipeline.selection import (
    POLYMARKET_WHALE_SELECTION_COMPLETED,
    POLYMARKET_WHALE_SELECTION_FAILED,
    POLYMARKET_WHALE_SELECTION_REQUESTED,
    POLYMARKET_WHALE_SELECTION_STARTED,
)


def test_whale_selection_pipeline_event_contract() -> None:
    assert POLYMARKET_WHALE_SELECTION_REQUESTED == "pipeline.selection.whales.requested"
    assert POLYMARKET_WHALE_SELECTION_STARTED == "pipeline.selection.whales.started"
    assert POLYMARKET_WHALE_SELECTION_COMPLETED == "pipeline.selection.whales.completed"
    assert POLYMARKET_WHALE_SELECTION_FAILED == "pipeline.selection.whales.failed"
