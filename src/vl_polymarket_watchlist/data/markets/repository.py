from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from vl_polymarket_watchlist.core.db.engine import database_session
from vl_polymarket_watchlist.core.db.models import (
    MarketDiscoveryObservation,
    MarketDiscoveryRun,
    PolymarketCondition,
    PolymarketToken,
)
from vl_polymarket_watchlist.core.time import ensure_utc
from vl_polymarket_watchlist.data.markets.market import (
    MarketObservation,
)


def persist_discovery_run(
    *,
    run_id: str,
    source: str,
    source_version: str,
    status: str,
    started_at: datetime,
    finished_at: datetime | None,
    generated_at: datetime,
    config_json: dict[str, Any],
    input_refs_json: dict[str, Any] | None = None,
    checked_count: int,
    observations: list[MarketObservation],
    error_count: int,
    error_message: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> int:
    started_at = ensure_utc(started_at)
    finished_at = ensure_utc(finished_at) if finished_at is not None else None
    generated_at = ensure_utc(generated_at)

    with database_session() as session:
        session.add(
            MarketDiscoveryRun(
                run_id=run_id,
                source=source,
                source_version=source_version,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                generated_at=generated_at,
                config_json=config_json,
                input_refs_json=input_refs_json or {},
                checked_count=checked_count,
                observed_count=len(observations),
                error_count=error_count,
                error_message=error_message,
                metadata_json=metadata_json or {},
            )
        )
        session.flush()

        for observation in observations:
            _upsert_condition(
                session=session,
                observation=observation,
                seen_at=generated_at,
            )
            _upsert_token(
                session=session,
                observation=observation,
                seen_at=generated_at,
            )
            session.add(_observation_row(run_id=run_id, observation=observation))

        session.commit()
        return len(observations)


def get_latest_discovery_run_id(*, source: str | None = None) -> str | None:
    with database_session() as session:
        statement = (
            select(MarketDiscoveryRun)
            .where(MarketDiscoveryRun.status == "completed")
            .order_by(
                MarketDiscoveryRun.generated_at.desc(),
                MarketDiscoveryRun.run_id.desc(),
            )
            .limit(1)
        )
        if source is not None:
            statement = statement.where(MarketDiscoveryRun.source == source)

        run = session.scalar(statement)

    return run.run_id if run is not None else None


def _upsert_condition(
    *,
    session,
    observation: MarketObservation,
    seen_at: datetime,
) -> None:
    payload = observation.condition
    row = session.get(PolymarketCondition, payload.condition_id)
    if row is None:
        session.add(
            PolymarketCondition(
                condition_id=payload.condition_id,
                event_id=payload.event_id,
                slug=payload.slug,
                title=payload.title,
                question=payload.question,
                end_date=payload.end_date,
                active=payload.active,
                closed=payload.closed,
                archived=payload.archived,
                enable_order_book=payload.enable_order_book,
                category=payload.category,
                tags=payload.tags,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                raw_latest_payload=payload.raw_latest_payload,
                updated_at=seen_at,
            )
        )
        return

    row.event_id = payload.event_id
    row.slug = payload.slug
    row.title = payload.title
    row.question = payload.question
    row.end_date = payload.end_date
    row.active = payload.active
    row.closed = payload.closed
    row.archived = payload.archived
    row.enable_order_book = payload.enable_order_book
    row.category = payload.category
    row.tags = payload.tags
    row.last_seen_at = seen_at
    row.raw_latest_payload = payload.raw_latest_payload
    row.updated_at = seen_at


def _upsert_token(
    *,
    session,
    observation: MarketObservation,
    seen_at: datetime,
) -> None:
    payload = observation.token
    row = session.get(PolymarketToken, payload.token_id)
    if row is None:
        session.add(
            PolymarketToken(
                token_id=payload.token_id,
                condition_id=payload.condition_id,
                outcome=payload.outcome,
                outcome_index=payload.outcome_index,
                opposite_token_id=payload.opposite_token_id,
                opposite_outcome=payload.opposite_outcome,
                active=payload.active,
                closed=payload.closed,
                enable_order_book=payload.enable_order_book,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                updated_at=seen_at,
            )
        )
        return

    row.condition_id = payload.condition_id
    row.outcome = payload.outcome
    row.outcome_index = payload.outcome_index
    row.opposite_token_id = payload.opposite_token_id
    row.opposite_outcome = payload.opposite_outcome
    row.active = payload.active
    row.closed = payload.closed
    row.enable_order_book = payload.enable_order_book
    row.last_seen_at = seen_at
    row.updated_at = seen_at


def _observation_row(
    *,
    run_id: str,
    observation: MarketObservation,
) -> MarketDiscoveryObservation:
    condition = observation.condition
    token = observation.token
    return MarketDiscoveryObservation(
        run_id=run_id,
        source=observation.source,
        observed_at=ensure_utc(observation.observed_at),
        condition_id=condition.condition_id,
        token_id=token.token_id,
        slug=condition.slug,
        title=condition.title,
        outcome=token.outcome,
        event_id=condition.event_id,
        event_slug=observation.event_slug,
        event_title=observation.event_title,
        end_date=condition.end_date,
        active=condition.active and token.active,
        closed=condition.closed or token.closed,
        archived=condition.archived,
        enable_order_book=condition.enable_order_book and token.enable_order_book,
        volume=observation.volume,
        liquidity=observation.liquidity,
        open_interest=observation.open_interest,
        last_trade_price=observation.last_trade_price,
        outcome_price=observation.outcome_price,
        source_reason=observation.source_reason,
        source_score=observation.source_score,
        metadata_json=observation.metadata_json,
        raw_payload=observation.raw_payload,
    )
