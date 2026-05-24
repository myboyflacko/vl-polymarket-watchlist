from __future__ import annotations

from pathlib import Path

from void_liquidity.adapters.polymarket.sources.track_whales import (
    WhaleTracker,
    load_workflow_profile,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.plugins import PluginSpec
from void_liquidity.features.whales.events import (
    TRACK_WHALES_COMPLETED,
    TRACK_WHALES_FAILED,
    TRACK_WHALES_REQUESTED,
    TRACK_WHALES_STARTED,
)


class PolymarketWhaleTrackingPlugin:
    spec = PluginSpec(
        name="polymarket.whale_tracking",
        version="1.0.0",
        description="Discovers qualified Polymarket whales and persists snapshots.",
        consumes=(TRACK_WHALES_REQUESTED,),
        produces=(
            TRACK_WHALES_STARTED,
            TRACK_WHALES_COMPLETED,
            TRACK_WHALES_FAILED,
        ),
    )

    async def handle(self, event: DomainEvent, bus: EventBus) -> None:
        profile_path = event.payload.get("profile_path")
        profile = (
            load_workflow_profile(Path(profile_path))
            if isinstance(profile_path, str)
            else load_workflow_profile()
        )
        tracker = WhaleTracker(profile=profile, event_bus=bus)
        await tracker.run(correlation_id=event.correlation_id)
