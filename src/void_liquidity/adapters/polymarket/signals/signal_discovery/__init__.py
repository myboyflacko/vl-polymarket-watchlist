__all__ = [
    "WhaleTracker",
    "WhaleTrackingProfile",
    "load_workflow_profile",
]


def __getattr__(name: str):
    if name == "load_workflow_profile":
        from void_liquidity.adapters.polymarket.signals.signal_discovery.config import (
            load_workflow_profile,
        )

        return load_workflow_profile

    if name == "WhaleTrackingProfile":
        from void_liquidity.adapters.polymarket.signals.signal_discovery.schemas import (
            WhaleTrackingProfile,
        )

        return WhaleTrackingProfile

    if name == "WhaleTracker":
        from void_liquidity.adapters.polymarket.signals.signal_discovery.tracker import (
            WhaleTracker,
        )

        return WhaleTracker

    raise AttributeError(name)
