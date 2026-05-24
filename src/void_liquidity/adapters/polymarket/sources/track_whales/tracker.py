from importlib import import_module
import sys

_module = import_module("void_liquidity.adapters.polymarket.collectors.whales.tracker")


if __name__ == "__main__":
    _module.main()
else:
    sys.modules[__name__] = _module
