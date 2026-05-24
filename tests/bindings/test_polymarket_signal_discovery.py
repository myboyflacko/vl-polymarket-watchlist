from void_liquidity.pipeline.signal_discovery.events import SIGNAL_DISCOVERY_REQUESTED
from void_liquidity.bindings.polymarket.signal_discovery import (
    PolymarketSignalDiscoveryBinding,
)


def test_polymarket_whale_binding_declares_runtime_contract() -> None:
    binding = PolymarketSignalDiscoveryBinding()

    assert binding.spec.name == "polymarket.signal_discovery"
    assert binding.spec.consumes == (SIGNAL_DISCOVERY_REQUESTED,)
    assert "pipeline.signal_discovery.completed" in binding.spec.produces
