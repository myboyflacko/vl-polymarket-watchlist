from void_liquidity.features.whales.events import WHALES_COLLECTION_REQUESTED
from void_liquidity.plugins.polymarket.whales import PolymarketWhaleCollectorPlugin


def test_polymarket_whale_plugin_declares_runtime_contract() -> None:
    plugin = PolymarketWhaleCollectorPlugin()

    assert plugin.spec.name == "polymarket.whale_collector"
    assert plugin.spec.consumes == (WHALES_COLLECTION_REQUESTED,)
    assert "whales.collection.completed" in plugin.spec.produces
