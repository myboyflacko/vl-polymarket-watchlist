from __future__ import annotations

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import MarketCandidate
from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales.candidates.repository import (
    get_latest_market_candidate_run,
    list_market_candidates,
    list_latest_market_candidates,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    QualifiedMarket,
    QualifiedMarketResult,
    WhaleQualifiedMarketProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.repository import (
    list_latest_qualified_markets,
    list_qualified_markets as list_persisted_qualified_markets,
    persist_qualified_market_run,
)


def list_qualified_markets(
    profile: WhaleQualifiedMarketProfile,
    *,
    candidate_run_id: str | None = None,
    limit: int | None = None,
) -> QualifiedMarketResult:
    candidates = (
        list_market_candidates(candidate_run_id)
        if candidate_run_id is not None
        else list_latest_market_candidates()
    )
    qualified_markets = [
        qualified_market
        for candidate in candidates
        if (
            qualified_market := _qualified_market(
                candidate=candidate,
                profile=profile,
            )
        )
        is not None
    ]
    sorted_markets = sorted(
        qualified_markets,
        key=lambda qualified_market: qualified_market.score,
        reverse=True,
    )
    if limit is not None:
        sorted_markets = sorted_markets[:limit]

    return QualifiedMarketResult(profile=profile, qualified_markets=sorted_markets)


def _qualified_market(
    *,
    candidate: MarketCandidate,
    profile: WhaleQualifiedMarketProfile,
) -> QualifiedMarket | None:
    price_delta = candidate.cur_price - candidate.weighted_avg_price
    value_per_wallet = (
        candidate.total_current_value / candidate.whale_count
        if candidate.whale_count
        else 0.0
    )
    price_delta_pct = (
        price_delta / candidate.weighted_avg_price
        if candidate.weighted_avg_price
        else None
    )

    if candidate.total_current_value < profile.min_total_current_value:
        return None

    if value_per_wallet < profile.min_value_per_wallet:
        return None

    match profile.name:
        case "confirmed":
            if price_delta <= 0:
                return None
            score = price_delta * value_per_wallet
        case "pain":
            if price_delta >= 0:
                return None
            score = abs(price_delta) * value_per_wallet
        case "high_value":
            score = candidate.total_current_value
        case "value_per_wallet":
            score = value_per_wallet

    return QualifiedMarket(
        profile=profile.name,
        candidate=candidate,
        score=score,
        price_delta=price_delta,
        price_delta_pct=price_delta_pct,
        value_per_wallet=value_per_wallet,
    )


class WhaleQualifiedMarketService:
    def __init__(self, profile: WhaleQualifiedMarketProfile) -> None:
        self.profile = profile

    def run(
        self,
        *,
        candidate_run_id: str | None = None,
        limit: int | None = None,
    ) -> QualifiedMarketResult:
        return list_qualified_markets(
            self.profile,
            candidate_run_id=candidate_run_id,
            limit=limit,
        )

    def persist(
        self,
        *,
        result: QualifiedMarketResult,
        run_id: str,
        candidate_run_id: str | None = None,
        generated_at: datetime | None = None,
        limit: int | None = None,
    ) -> None:
        actual_candidate_run_id = candidate_run_id
        if actual_candidate_run_id is None:
            latest_candidate_run = get_latest_market_candidate_run()
            if latest_candidate_run is None:
                raise ValueError("candidate_run_id is required without candidate runs")
            actual_candidate_run_id = latest_candidate_run.run_id

        persist_qualified_market_run(
            profile=self.profile,
            run_id=run_id,
            candidate_run_id=actual_candidate_run_id,
            generated_at=generated_at or datetime.now(UTC),
            result=result,
            limit=limit,
        )

    def list(
        self,
        *,
        run_id: str | None = None,
        limit: int | None = None,
    ) -> QualifiedMarketResult:
        if run_id is None:
            persisted = list_latest_qualified_markets()
        else:
            persisted = list_persisted_qualified_markets(run_id)

        if limit is None:
            return persisted

        return persisted.model_copy(
            update={"qualified_markets": persisted.qualified_markets[:limit]},
        )
