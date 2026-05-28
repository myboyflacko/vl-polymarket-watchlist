from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy import select

from void_liquidity.adapters.polymarket.discovery.whales.models import TrackedWhale
from void_liquidity.adapters.polymarket.markets.whales.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.models import (
    WhaleMarket,
    WhaleMarketCandidateRun,
    WhaleMarketMetricSnapshot,
)
from void_liquidity.data import database_session


def list_tracked_whale_wallets() -> list[str]:
    with database_session() as session:
        return list(
            session.scalars(
                select(TrackedWhale.proxy_wallet).order_by(TrackedWhale.id)
            )
        )


def persist_market_candidates(
    candidates: Iterable[MarketCandidate],
    *,
    run_id: str,
    min_whale_count: int,
    position_count: int,
    error_count: int,
    seen_at: datetime | None = None,
) -> None:
    actual_seen_at = seen_at or datetime.now(UTC)
    candidate_list = list(candidates)

    with database_session() as session:
        session.merge(
            WhaleMarketCandidateRun(
                run_id=run_id,
                generated_at=actual_seen_at,
                min_whale_count=min_whale_count,
                candidate_count=len(candidate_list),
                position_count=position_count,
                error_count=error_count,
            )
        )
        _upsert_markets(
            candidates=candidate_list,
            seen_at=actual_seen_at,
            session=session,
        )
        _upsert_metric_snapshots(
            candidates=candidate_list,
            run_id=run_id,
            generated_at=actual_seen_at,
            session=session,
        )
        session.commit()


def _upsert_markets(
    *,
    candidates: list[MarketCandidate],
    seen_at: datetime,
    session,
) -> None:
    rows = [
        _market_row(candidate=candidate, seen_at=seen_at)
        for candidate in candidates
    ]
    if not rows:
        return

    statement = insert(WhaleMarket).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"token_id", "first_seen_at"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[WhaleMarket.token_id],
            set_=update_columns,
        )
    )


def _upsert_metric_snapshots(
    *,
    candidates: list[MarketCandidate],
    run_id: str,
    generated_at: datetime,
    session,
) -> None:
    rows = [
        _snapshot_row(
            candidate=candidate,
            run_id=run_id,
            generated_at=generated_at,
        )
        for candidate in candidates
    ]
    if not rows:
        return

    statement = insert(WhaleMarketMetricSnapshot).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "token_id"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                WhaleMarketMetricSnapshot.run_id,
                WhaleMarketMetricSnapshot.token_id,
            ],
            set_=update_columns,
        )
    )


def _market_row(*, candidate: MarketCandidate, seen_at: datetime) -> dict:
    return {
        "token_id": candidate.token_id,
        "condition_id": candidate.condition_id,
        "title": candidate.title,
        "slug": candidate.slug,
        "outcome": candidate.outcome,
        "opposite_token_id": candidate.opposite_token_id,
        "opposite_outcome": candidate.opposite_outcome,
        "end_date": candidate.end_date,
        "negative_risk": candidate.negative_risk,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
    }


def _snapshot_row(
    *,
    candidate: MarketCandidate,
    run_id: str,
    generated_at: datetime,
) -> dict:
    return {
        "run_id": run_id,
        "token_id": candidate.token_id,
        "whale_count": candidate.whale_count,
        "wallets": candidate.wallets,
        "total_size": candidate.total_size,
        "total_current_value": candidate.total_current_value,
        "weighted_avg_price": candidate.weighted_avg_price,
        "cur_price": candidate.cur_price,
        "generated_at": generated_at,
    }
