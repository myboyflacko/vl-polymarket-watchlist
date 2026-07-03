from __future__ import annotations

from vl_polymarket_watchlist.markets.discovery.strategies.whale_leaderboard import (
    WhaleDiscoverySource,
)


def build_source(name: str) -> WhaleDiscoverySource:
    if name in {"whale_discovery", "leaderboard_current_positions"}:
        return WhaleDiscoverySource()

    raise ValueError(f"Unknown market discovery source: {name}")
