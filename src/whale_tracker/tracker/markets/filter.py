from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel, Field

from whale_tracker.tracker.markets.domain import (
    Market,
    MarketObservation,
    WhalePosition,
)


class TrackedMarketFilterProfile(BaseModel):
    name: str = "dominant_side_5_whales_80_percent_latest_run"
    min_whale_count: int = Field(default=5, ge=1)
    min_dominance_ratio: float = Field(default=0.8, ge=0.0, le=1.0)

    def run(self, markets: Iterable[Market]) -> list[Market]:
        grouped: dict[str, list[Market]] = defaultdict(list)
        for market in markets:
            grouped[market.condition_id].append(market)

        tracked: list[Market] = []
        for group_markets in grouped.values():
            total_wallets = {
                wallet for market in group_markets for wallet in market.wallets
            }
            if not total_wallets:
                continue

            dominant = max(
                group_markets,
                key=lambda market: (market.whale_count, market.total_current_value),
            )
            dominance_ratio = dominant.whale_count / len(total_wallets)
            if (
                dominant.whale_count >= self.min_whale_count
                and dominance_ratio >= self.min_dominance_ratio
            ):
                tracked.append(dominant)

        return sorted(
            tracked,
            key=lambda market: (market.whale_count, market.total_current_value),
            reverse=True,
        )

    def run_observations(
        self,
        observations: Iterable[MarketObservation],
    ) -> list[Market]:
        return self.run(build_market_candidates_from_observations(observations))


def build_market_candidates(positions: Iterable[WhalePosition]) -> list[Market]:
    grouped: dict[str, list[WhalePosition]] = defaultdict(list)
    for position in positions:
        grouped[position.token_id].append(position)

    return [
        build_market_candidate(token_id=token_id, positions=group_positions)
        for token_id, group_positions in grouped.items()
    ]


def build_market_observations(
    *,
    positions: Iterable[WhalePosition],
    generated_at: datetime,
) -> list[MarketObservation]:
    return [
        MarketObservation(
            proxy_wallet=position.proxy_wallet,
            token_id=position.token_id,
            condition_id=position.condition_id,
            title=position.title,
            slug=position.slug,
            outcome=position.outcome,
            size=position.size,
            current_value=position.current_value,
            avg_price=position.avg_price,
            cur_price=position.cur_price,
            opposite_token_id=position.opposite_token_id,
            opposite_outcome=position.opposite_outcome,
            end_date=position.end_date,
            negative_risk=position.negative_risk,
            generated_at=generated_at,
        )
        for position in positions
    ]


def build_market_candidates_from_observations(
    observations: Iterable[MarketObservation],
) -> list[Market]:
    grouped: dict[str, list[MarketObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.token_id].append(observation)

    return [
        build_market_candidate_from_observations(
            token_id=token_id,
            observations=group_observations,
        )
        for token_id, group_observations in grouped.items()
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


def build_market_candidate_from_observations(
    *,
    token_id: str,
    observations: list[MarketObservation],
) -> Market:
    first_observation = observations[0]
    total_size = sum(observation.size for observation in observations)
    total_current_value = sum(observation.current_value for observation in observations)
    wallets = list(dict.fromkeys(observation.proxy_wallet for observation in observations))
    weighted_avg_price = (
        sum(observation.avg_price * observation.size for observation in observations)
        / total_size
        if total_size
        else 0.0
    )

    return Market(
        token_id=token_id,
        condition_id=first_observation.condition_id,
        title=first_observation.title,
        slug=first_observation.slug,
        outcome=first_observation.outcome,
        whale_count=len(wallets),
        wallets=wallets,
        total_size=total_size,
        total_current_value=total_current_value,
        weighted_avg_price=weighted_avg_price,
        cur_price=first_observation.cur_price,
        opposite_token_id=first_observation.opposite_token_id,
        opposite_outcome=first_observation.opposite_outcome,
        end_date=first_observation.end_date,
        negative_risk=first_observation.negative_risk,
    )
