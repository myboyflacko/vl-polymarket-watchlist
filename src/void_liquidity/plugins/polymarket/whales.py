from __future__ import annotations

from pathlib import Path

from void_liquidity.adapters.polymarket.collectors.whales import (
    WhaleTracker,
    load_workflow_profile,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.plugins import PluginSpec
from void_liquidity.features.whales.events import (
    WHALES_COLLECTION_COMPLETED,
    WHALES_COLLECTION_FAILED,
    WHALES_COLLECTION_REQUESTED,
    WHALES_COLLECTION_STARTED,
)


class PolymarketWhaleCollectorPlugin:
    spec = PluginSpec(
        name="polymarket.whale_collector",
        version="1.0.0",
        description="Collects qualified Polymarket whales and persists snapshots.",
        consumes=(WHALES_COLLECTION_REQUESTED,),
        produces=(
            WHALES_COLLECTION_STARTED,
            WHALES_COLLECTION_COMPLETED,
            WHALES_COLLECTION_FAILED,
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
