from __future__ import annotations

from pathlib import Path

from void_liquidity.adapters.polymarket.signal_discovery.whales import (
    WhaleTracker,
    load_workflow_profile,
)
from void_liquidity.adapters.polymarket.signal_discovery.whales.events import (
    POLYMARKET_WHALES_DISCOVERED,
)
from void_liquidity.core.events import DomainEvent, EventBus
from void_liquidity.core.bindings import BindingSpec
from void_liquidity.pipeline.signal_discovery.events import (
    SIGNAL_DISCOVERY_COMPLETED,
    SIGNAL_DISCOVERY_FAILED,
    SIGNAL_DISCOVERY_REQUESTED,
    SIGNAL_DISCOVERY_STARTED,
)


class PolymarketSignalDiscoveryBinding:
    spec = BindingSpec(
        name="polymarket.signal_discovery",
        version="1.0.0",
        description="Collects qualified Polymarket whales and persists snapshots.",
        consumes=(SIGNAL_DISCOVERY_REQUESTED,),
        produces=(
            SIGNAL_DISCOVERY_STARTED,
            SIGNAL_DISCOVERY_COMPLETED,
            SIGNAL_DISCOVERY_FAILED,
            POLYMARKET_WHALES_DISCOVERED,
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
