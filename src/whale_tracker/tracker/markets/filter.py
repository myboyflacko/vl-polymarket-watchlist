from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel, Field

from whale_tracker.tracker.markets.domain import (
    Market,
    WhalePosition,
)


class TrackedMarketFilterProfile(BaseModel):
    name: str = "same_side_3_whales_unique_condition_v1"
    min_whale_count: int = Field(default=3, ge=1)

    def run(self, markets: Iterable[Market]) -> list[Market]:
        same_side_candidates = [
            market
            for market in markets
            if market.whale_count >= self.min_whale_count
        ]
        grouped: dict[str, list[Market]] = defaultdict(list)
        for market in same_side_candidates:
            grouped[market.condition_id].append(market)

        tracked = [
            group_markets[0]
            for group_markets in grouped.values()
            if len(group_markets) == 1
        ]
        return sorted(
            tracked,
            key=lambda market: (market.whale_count, market.total_current_value),
            reverse=True,
        )


def build_market_candidates(positions: Iterable[WhalePosition]) -> list[Market]:
    grouped: dict[str, list[WhalePosition]] = defaultdict(list)
    for position in positions:
        grouped[position.token_id].append(position)

    return [
        build_market_candidate(token_id=token_id, positions=group_positions)
        for token_id, group_positions in grouped.items()
    ]


def build_market_candidate(*, token_id: str, positions: list[WhalePosition]) -> Market:
    first_position = positions[0]
    total_size = sum(position.size for position in positions)
    total_current_value = sum(position.current_value for position in positions)
    wallets = list(dict.fromkeys(position.proxy_wallet for position in positions))
    weighted_avg_price = (
        sum(position.avg_price * position.size for position in positions) / total_size
        if total_size
        else 0.0
    )

    return Market(
        token_id=token_id,
        condition_id=first_position.condition_id,
        title=first_position.title,
        slug=first_position.slug,
        outcome=first_position.outcome,
        whale_count=len(wallets),
        wallets=wallets,
        total_size=total_size,
        total_current_value=total_current_value,
        weighted_avg_price=weighted_avg_price,
        cur_price=first_position.cur_price,
        opposite_token_id=first_position.opposite_token_id,
        opposite_outcome=first_position.opposite_outcome,
        end_date=first_position.end_date,
        negative_risk=first_position.negative_risk,
    )
