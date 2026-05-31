from void_liquidity.pipeline.signals import (
    POLYMARKET_WHALE_SIGNALS_COMPLETED,
    POLYMARKET_WHALE_SIGNALS_FAILED,
    POLYMARKET_WHALE_SIGNALS_REQUESTED,
    POLYMARKET_WHALE_SIGNALS_STARTED,
)


def test_whale_signals_pipeline_event_contract() -> None:
    assert POLYMARKET_WHALE_SIGNALS_REQUESTED == "pipeline.signals.whales.requested"
    assert POLYMARKET_WHALE_SIGNALS_STARTED == "pipeline.signals.whales.started"
    assert POLYMARKET_WHALE_SIGNALS_COMPLETED == "pipeline.signals.whales.completed"
    assert POLYMARKET_WHALE_SIGNALS_FAILED == "pipeline.signals.whales.failed"
