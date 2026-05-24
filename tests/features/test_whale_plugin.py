from void_liquidity.features.whales.events import TRACK_WHALES_REQUESTED
from void_liquidity.features.whales.polymarket import PolymarketWhaleTrackingPlugin


def test_polymarket_whale_plugin_declares_runtime_contract() -> None:
    plugin = PolymarketWhaleTrackingPlugin()

    assert plugin.spec.name == "polymarket.whale_tracking"
    assert plugin.spec.consumes == (TRACK_WHALES_REQUESTED,)
    assert "whales.tracking.completed" in plugin.spec.produces
