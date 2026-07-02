from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from polymarket_storage.core.db.engine import database_session
from polymarket_storage.core.time import ensure_utc
from polymarket_storage.market_acquisition.domain import Market as MarketPayload
from polymarket_storage.market_acquisition.models import (
    CollectorRun,
    CollectorRunMarket,
    Market,
)


def persist_collector_run(
    *,
    run_id: str,
    strategy_name: str,
    strategy_params: dict[str, Any],
    generated_at: datetime,
    checked_market_count: int,
    markets: list[MarketPayload],
) -> int:
    generated_at = ensure_utc(generated_at)

    with database_session() as session:
        run = CollectorRun(
            run_id=run_id,
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            status="completed",
            generated_at=generated_at,
            checked_market_count=checked_market_count,
            stored_market_count=0,
        )
        session.add(run)
        session.flush()

        market_ids = []
        for market in markets:
            row = _upsert_market(session=session, payload=market, seen_at=generated_at)
            market_ids.append(row.id)

        for market_id in dict.fromkeys(market_ids):
            session.add(
                CollectorRunMarket(
                    run_id=run_id,
                    market_id=market_id,
                    generated_at=generated_at,
                )
            )

        run.stored_market_count = len(set(market_ids))
        session.commit()
        return run.stored_market_count


def get_latest_collector_run_id() -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(CollectorRun)
            .where(CollectorRun.status == "completed")
            .order_by(CollectorRun.generated_at.desc(), CollectorRun.run_id.desc())
            .limit(1)
        )

    return run.run_id if run is not None else None


def list_markets_for_run(run_id: str) -> list[MarketPayload]:
    with database_session() as session:
        rows = list(
            session.scalars(
                select(Market)
                .join(CollectorRunMarket, CollectorRunMarket.market_id == Market.id)
                .where(CollectorRunMarket.run_id == run_id)
                .order_by(Market.id)
            )
        )

    return [_payload_from_row(row) for row in rows]


def _upsert_market(
    *,
    session,
    payload: MarketPayload,
    seen_at: datetime,
) -> Market:
    row = session.scalar(select(Market).where(Market.token_id == payload.token_id))
    if row is None:
        row = Market(
            token_id=payload.token_id,
            condition_id=payload.condition_id,
            title=payload.title,
            slug=payload.slug,
            outcome=payload.outcome,
            opposite_token_id=payload.opposite_token_id,
            opposite_outcome=payload.opposite_outcome,
            end_date=payload.end_date,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        session.add(row)
        session.flush()
        return row

    row.condition_id = payload.condition_id
    row.title = payload.title
    row.slug = payload.slug
    row.outcome = payload.outcome
    row.opposite_token_id = payload.opposite_token_id
    row.opposite_outcome = payload.opposite_outcome
    row.end_date = payload.end_date
    row.last_seen_at = seen_at
    session.flush()
    return row


def _payload_from_row(row: Market) -> MarketPayload:
    return MarketPayload(
        token_id=row.token_id,
        condition_id=row.condition_id,
        title=row.title,
        slug=row.slug,
        outcome=row.outcome,
        opposite_token_id=row.opposite_token_id,
        opposite_outcome=row.opposite_outcome,
        end_date=row.end_date,
    )
