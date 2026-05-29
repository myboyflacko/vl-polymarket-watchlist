__all__ = [
    "WhaleTrackerV2",
    "WhaleTrackerV2Profile",
    "Whales",
]


def __getattr__(name: str):
    if name == "WhaleTrackerV2":
        from void_liquidity.adapters.polymarket.discovery.whales.tracker import (
            WhaleTrackerV2,
        )

        return WhaleTrackerV2

    if name == "WhaleTrackerV2Profile":
        from void_liquidity.adapters.polymarket.discovery.whales.profiles import (
            WhaleTrackerV2Profile,
        )

        return WhaleTrackerV2Profile

    if name == "Whales":
        from void_liquidity.adapters.polymarket.discovery.whales.domain import Whales

        return Whales

    raise AttributeError(name)
