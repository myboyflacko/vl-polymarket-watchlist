from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy import select

from void_liquidity.adapters.polymarket.discovery.whales.models import TrackedWhale
from void_liquidity.adapters.polymarket.markets.whales.domain import MarketCandidate
from void_liquidity.adapters.polymarket.markets.whales.models import (
    WhaleMarketCandidate,
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
    seen_at: datetime | None = None,
) -> None:
    actual_seen_at = seen_at or datetime.now(UTC)
    rows = [
        _candidate_row(candidate=candidate, seen_at=actual_seen_at)
        for candidate in candidates
    ]

    if not rows:
        return

    statement = insert(WhaleMarketCandidate).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"token_id", "first_seen_at"}
    }

    with database_session() as session:
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[WhaleMarketCandidate.token_id],
                set_=update_columns,
            )
        )
        session.commit()


def _candidate_row(
    *,
    candidate: MarketCandidate,
    seen_at: datetime,
) -> dict:
    return {
        "token_id": candidate.token_id,
        "condition_id": candidate.condition_id,
        "title": candidate.title,
        "slug": candidate.slug,
        "outcome": candidate.outcome,
        "whale_count": candidate.whale_count,
        "wallets": candidate.wallets,
        "total_size": candidate.total_size,
        "total_current_value": candidate.total_current_value,
        "weighted_avg_price": candidate.weighted_avg_price,
        "cur_price": candidate.cur_price,
        "opposite_token_id": candidate.opposite_token_id,
        "opposite_outcome": candidate.opposite_outcome,
        "end_date": candidate.end_date,
        "negative_risk": candidate.negative_risk,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
    }
