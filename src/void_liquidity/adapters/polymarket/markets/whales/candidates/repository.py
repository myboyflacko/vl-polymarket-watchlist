from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import (
    MarketCandidate,
    WhaleMarketCandidateRunSummary,
    WhaleMarketSnapshot,
)
from void_liquidity.adapters.polymarket.markets.whales.candidates.models import (
    WhaleMarket,
    WhaleMarketCandidateRun,
    WhaleMarketMetricSnapshot,
)
from void_liquidity.data.engine import database_session


def get_latest_market_candidate_run() -> WhaleMarketCandidateRunSummary | None:
    with database_session() as session:
        run = session.scalar(_latest_run_statement())

    if run is None:
        return None

    return _run_summary(run)


def list_latest_market_candidates(
    *,
    limit: int | None = None,
) -> list[MarketCandidate]:
    latest_run = get_latest_market_candidate_run()
    if latest_run is None:
        return []

    with database_session() as session:
        statement = (
            select(WhaleMarket, WhaleMarketMetricSnapshot)
            .join(
                WhaleMarketMetricSnapshot,
                WhaleMarketMetricSnapshot.identity_id == WhaleMarket.id,
            )
            .where(WhaleMarketMetricSnapshot.run_id == latest_run.run_id)
            .order_by(
                WhaleMarketMetricSnapshot.whale_count.desc(),
                WhaleMarketMetricSnapshot.total_current_value.desc(),
            )
        )
        if limit is not None:
            statement = statement.limit(limit)

        rows = session.execute(statement).all()

    return [
        _market_candidate(market=market, snapshot=snapshot)
        for market, snapshot in rows
    ]


def list_market_candidates(
    run_id: str,
    *,
    limit: int | None = None,
) -> list[MarketCandidate]:
    with database_session() as session:
        statement = (
            select(WhaleMarket, WhaleMarketMetricSnapshot)
            .join(
                WhaleMarketMetricSnapshot,
                WhaleMarketMetricSnapshot.identity_id == WhaleMarket.id,
            )
            .where(WhaleMarketMetricSnapshot.run_id == run_id)
            .order_by(
                WhaleMarketMetricSnapshot.whale_count.desc(),
                WhaleMarketMetricSnapshot.total_current_value.desc(),
            )
        )
        if limit is not None:
            statement = statement.limit(limit)

        rows = session.execute(statement).all()

    return [
        _market_candidate(market=market, snapshot=snapshot)
        for market, snapshot in rows
    ]


def list_market_snapshots(
    token_id: str,
    *,
    limit: int | None = None,
) -> list[WhaleMarketSnapshot]:
    with database_session() as session:
        statement = (
            select(WhaleMarket, WhaleMarketMetricSnapshot)
            .join(
                WhaleMarketMetricSnapshot,
                WhaleMarketMetricSnapshot.identity_id == WhaleMarket.id,
            )
            .where(WhaleMarket.token_id == token_id)
            .order_by(
                WhaleMarketMetricSnapshot.generated_at.desc(),
                WhaleMarketMetricSnapshot.run_id.desc(),
            )
        )
        if limit is not None:
            statement = statement.limit(limit)

        rows = session.execute(statement).all()

    return [
        _market_snapshot(market=market, snapshot=snapshot)
        for market, snapshot in rows
    ]


def persist_market_candidates(
    candidates: Iterable[MarketCandidate],
    *,
    run_id: str,
    selection_run_id: str,
    min_whale_count: int,
    position_count: int,
    error_count: int,
    seen_at: datetime | None = None,
) -> None:
    actual_seen_at = seen_at or datetime.now(UTC)
    candidate_list = list(candidates)

    with database_session() as session:
        session.add(
            WhaleMarketCandidateRun(
                run_id=run_id,
                selection_run_id=selection_run_id,
                status="completed",
                config_key=market_candidate_config_key(
                    min_whale_count=min_whale_count,
                ),
                generated_at=actual_seen_at,
                min_whale_count=min_whale_count,
                candidate_count=len(candidate_list),
                position_count=position_count,
                error_count=error_count,
            )
        )
        identity_ids = _upsert_markets(
            candidates=candidate_list,
            seen_at=actual_seen_at,
            session=session,
        )
        _upsert_metric_snapshots(
            candidates=candidate_list,
            run_id=run_id,
            generated_at=actual_seen_at,
            session=session,
            identity_ids=identity_ids,
        )
        session.commit()


def get_completed_market_candidate_run_for_parent(
    *,
    selection_run_id: str,
    min_whale_count: int,
) -> WhaleMarketCandidateRunSummary | None:
    with database_session() as session:
        run = session.scalar(
            select(WhaleMarketCandidateRun)
            .where(
                WhaleMarketCandidateRun.selection_run_id == selection_run_id,
                WhaleMarketCandidateRun.config_key
                == market_candidate_config_key(min_whale_count=min_whale_count),
                WhaleMarketCandidateRun.status == "completed",
            )
            .order_by(
                WhaleMarketCandidateRun.generated_at.desc(),
                WhaleMarketCandidateRun.run_id.desc(),
            )
            .limit(1)
        )

    return _run_summary(run) if run is not None else None


def persist_failed_market_candidates(
    *,
    run_id: str,
    selection_run_id: str,
    min_whale_count: int,
    generated_at: datetime,
    error_type: str,
    error: str,
) -> None:
    with database_session() as session:
        session.add(
            WhaleMarketCandidateRun(
                run_id=run_id,
                selection_run_id=selection_run_id,
                status="failed",
                config_key=market_candidate_config_key(
                    min_whale_count=min_whale_count,
                ),
                generated_at=generated_at,
                min_whale_count=min_whale_count,
                candidate_count=0,
                position_count=0,
                error_count=0,
                error_type=error_type,
                error=error,
            )
        )
        session.commit()


def _latest_run_statement():
    return (
        select(WhaleMarketCandidateRun)
        .where(WhaleMarketCandidateRun.status == "completed")
        .order_by(
            WhaleMarketCandidateRun.generated_at.desc(),
            WhaleMarketCandidateRun.run_id.desc(),
        )
        .limit(1)
    )


def _run_summary(run: WhaleMarketCandidateRun) -> WhaleMarketCandidateRunSummary:
    return WhaleMarketCandidateRunSummary(
        run_id=run.run_id,
        selection_run_id=run.selection_run_id,
        generated_at=run.generated_at,
        min_whale_count=run.min_whale_count,
        candidate_count=run.candidate_count,
        position_count=run.position_count,
        error_count=run.error_count,
    )


def _market_candidate(
    *,
    market: WhaleMarket,
    snapshot: WhaleMarketMetricSnapshot,
) -> MarketCandidate:
    return MarketCandidate(
        token_id=market.token_id,
        condition_id=market.condition_id,
        title=market.title,
        slug=market.slug,
        outcome=market.outcome,
        whale_count=snapshot.whale_count,
        wallets=snapshot.wallets,
        total_size=snapshot.total_size,
        total_current_value=snapshot.total_current_value,
        weighted_avg_price=snapshot.weighted_avg_price,
        cur_price=snapshot.cur_price,
        opposite_token_id=market.opposite_token_id,
        opposite_outcome=market.opposite_outcome,
        end_date=market.end_date,
        negative_risk=market.negative_risk,
    )


def _market_snapshot(
    *,
    market: WhaleMarket,
    snapshot: WhaleMarketMetricSnapshot,
) -> WhaleMarketSnapshot:
    return WhaleMarketSnapshot(
        run_id=snapshot.run_id,
        generated_at=snapshot.generated_at,
        token_id=market.token_id,
        condition_id=market.condition_id,
        title=market.title,
        slug=market.slug,
        outcome=market.outcome,
        whale_count=snapshot.whale_count,
        wallets=snapshot.wallets,
        total_size=snapshot.total_size,
        total_current_value=snapshot.total_current_value,
        weighted_avg_price=snapshot.weighted_avg_price,
        cur_price=snapshot.cur_price,
        opposite_token_id=market.opposite_token_id,
        opposite_outcome=market.opposite_outcome,
        end_date=market.end_date,
        negative_risk=market.negative_risk,
    )


def _upsert_markets(
    *,
    candidates: list[MarketCandidate],
    seen_at: datetime,
    session,
) -> dict[str, int]:
    rows = [
        _market_row(candidate=candidate, seen_at=seen_at)
        for candidate in candidates
    ]
    if not rows:
        return {}

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
    return dict(
        session.execute(
            select(WhaleMarket.token_id, WhaleMarket.id).where(
                WhaleMarket.token_id.in_([row["token_id"] for row in rows])
            )
        ).all()
    )


def _upsert_metric_snapshots(
    *,
    candidates: list[MarketCandidate],
    run_id: str,
    generated_at: datetime,
    session,
    identity_ids: dict[str, int],
) -> None:
    rows = [
        _snapshot_row(
            candidate=candidate,
            run_id=run_id,
            generated_at=generated_at,
            identity_id=identity_ids[candidate.token_id],
        )
        for candidate in candidates
    ]
    if not rows:
        return

    statement = insert(WhaleMarketMetricSnapshot).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "identity_id"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                WhaleMarketMetricSnapshot.run_id,
                WhaleMarketMetricSnapshot.identity_id,
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
    identity_id: int,
) -> dict:
    return {
        "run_id": run_id,
        "identity_id": identity_id,
        "whale_count": candidate.whale_count,
        "wallets": candidate.wallets,
        "total_size": candidate.total_size,
        "total_current_value": candidate.total_current_value,
        "weighted_avg_price": candidate.weighted_avg_price,
        "cur_price": candidate.cur_price,
        "generated_at": generated_at,
    }


def market_candidate_config_key(*, min_whale_count: int) -> str:
    return json.dumps(
        {"min_whale_count": min_whale_count},
        sort_keys=True,
        separators=(",", ":"),
    )
