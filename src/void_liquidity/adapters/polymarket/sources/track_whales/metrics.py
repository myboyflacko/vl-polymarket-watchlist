from importlib import import_module
import sys

sys.modules[__name__] = import_module(
    "void_liquidity.adapters.polymarket.collectors.whales.metrics"
)
