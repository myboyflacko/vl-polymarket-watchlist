from pathlib import Path

from void_liquidity.features.whales import WHALES_COLLECTION_REQUESTED
from void_liquidity.plugins.polymarket import PolymarketWhaleCollectorPlugin
from void_liquidity.workflows.track_whales import (
    build_track_whales_event,
    build_track_whales_runtime,
)


def test_build_track_whales_event_uses_feature_contract() -> None:
    event = build_track_whales_event(profile_path=Path("profile.json"))

    assert event.event_type == WHALES_COLLECTION_REQUESTED
    assert event.source == "workflow.track_whales"
    assert event.payload == {"profile_path": "profile.json"}


def test_build_track_whales_runtime_installs_polymarket_plugin() -> None:
    runtime = build_track_whales_runtime()

    assert isinstance(
        runtime.registry.get("polymarket.whale_collector"),
        PolymarketWhaleCollectorPlugin,
    )
