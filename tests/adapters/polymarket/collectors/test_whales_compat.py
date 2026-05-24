from void_liquidity.adapters.polymarket.collectors.whales import WhaleTracker
from void_liquidity.adapters.polymarket.sources.track_whales import (
    WhaleTracker as LegacyWhaleTracker,
)
from void_liquidity.adapters.polymarket.sources.track_whales.metrics import (
    _build_candidate_pool,
)


def test_legacy_track_whales_path_reexports_collector() -> None:
    assert LegacyWhaleTracker is WhaleTracker
    assert callable(_build_candidate_pool)
