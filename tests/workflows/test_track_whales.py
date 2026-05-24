from pathlib import Path

from void_liquidity.pipeline.signal_discovery import SIGNAL_DISCOVERY_REQUESTED
from void_liquidity.bindings.polymarket import PolymarketSignalDiscoveryBinding
from void_liquidity.workflows.track_whales import (
    build_track_whales_event,
    build_track_whales_runtime,
)


def test_build_track_whales_event_uses_pipeline_contract() -> None:
    event = build_track_whales_event(profile_path=Path("profile.json"))

    assert event.event_type == SIGNAL_DISCOVERY_REQUESTED
    assert event.source == "workflow.track_whales"
    assert event.payload == {"profile_path": "profile.json"}


def test_build_track_whales_runtime_installs_polymarket_binding() -> None:
    runtime = build_track_whales_runtime()

    assert isinstance(
        runtime.registry.get("polymarket.signal_discovery"),
        PolymarketSignalDiscoveryBinding,
    )
