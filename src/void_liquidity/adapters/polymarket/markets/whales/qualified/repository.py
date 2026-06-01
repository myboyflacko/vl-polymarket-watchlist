from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from void_liquidity.adapters.polymarket.markets.whales.candidates.domain import (
    MarketCandidate,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    QualifiedMarket,
    QualifiedMarketResult,
    WhaleQualifiedMarketProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.models import (
    QualifiedMarketIdentity,
    QualifiedMarketMetricSnapshot,
    QualifiedMarketRun,
)
from void_liquidity.data.engine import database_session


def get_latest_qualified_market_run_id() -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(QualifiedMarketRun)
            .where(QualifiedMarketRun.status == "completed")
            .order_by(
                QualifiedMarketRun.generated_at.desc(),
                QualifiedMarketRun.run_id.desc(),
            )
            .limit(1)
        )

    return run.run_id if run is not None else None


def persist_qualified_market_run(
    *,
    profiles: Sequence[WhaleQualifiedMarketProfile],
    run_id: str,
    candidate_run_id: str,
    generated_at: datetime,
    result: QualifiedMarketResult,
    limit: int | None = None,
) -> None:
    with database_session() as session:
        session.add(
            QualifiedMarketRun(
                run_id=run_id,
                candidate_run_id=candidate_run_id,
                status="completed",
                config_key=qualified_config_key(profiles=profiles, limit=limit),
                generated_at=generated_at,
                profiles=[profile.model_dump(mode="json") for profile in profiles],
                qualified_market_count=len(result.qualified_markets),
                limit=limit,
            )
        )
        identity_ids = _upsert_qualified_markets(
            session=session,
            markets=result.qualified_markets,
            seen_at=generated_at,
        )
        _upsert_metric_snapshots(
            session=session,
            markets=result.qualified_markets,
            run_id=run_id,
            generated_at=generated_at,
            identity_ids=identity_ids,
        )
        session.commit()


def get_completed_qualified_market_run_for_parent(
    *,
    candidate_run_id: str,
    profiles: Sequence[WhaleQualifiedMarketProfile],
    limit: int | None,
) -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(QualifiedMarketRun)
            .where(
                QualifiedMarketRun.candidate_run_id == candidate_run_id,
                QualifiedMarketRun.config_key
                == qualified_config_key(profiles=profiles, limit=limit),
                QualifiedMarketRun.status == "completed",
            )
            .order_by(
                QualifiedMarketRun.generated_at.desc(),
                QualifiedMarketRun.run_id.desc(),
            )
            .limit(1)
        )

    return run.run_id if run is not None else None


def persist_failed_qualified_market_run(
    *,
    profiles: Sequence[WhaleQualifiedMarketProfile],
    run_id: str,
    candidate_run_id: str,
    generated_at: datetime,
    limit: int | None,
    error_type: str,
    error: str,
) -> None:
    with database_session() as session:
        session.add(
            QualifiedMarketRun(
                run_id=run_id,
                candidate_run_id=candidate_run_id,
                status="failed",
                config_key=qualified_config_key(profiles=profiles, limit=limit),
                generated_at=generated_at,
                profiles=[profile.model_dump(mode="json") for profile in profiles],
                qualified_market_count=0,
                limit=limit,
                error_type=error_type,
                error=error,
            )
        )
        session.commit()


def list_qualified_markets(run_id: str) -> QualifiedMarketResult:
    with database_session() as session:
        run = session.get(QualifiedMarketRun, run_id)
        if run is None:
            return QualifiedMarketResult(
                profiles=[WhaleQualifiedMarketProfile(name="high_value")],
                qualified_markets=[],
            )
        rows = list(
            session.execute(
                select(QualifiedMarketIdentity, QualifiedMarketMetricSnapshot)
                .join(
                    QualifiedMarketMetricSnapshot,
                    QualifiedMarketMetricSnapshot.identity_id
                    == QualifiedMarketIdentity.id,
                )
                .where(QualifiedMarketMetricSnapshot.run_id == run_id)
                .order_by(QualifiedMarketMetricSnapshot.rank)
            )
        )

    profiles = [
        WhaleQualifiedMarketProfile.model_validate(profile)
        for profile in run.profiles
    ]
    return QualifiedMarketResult(
        profiles=profiles,
        qualified_markets=[
            QualifiedMarket(
                profile=snapshot.profile_name,
                candidate=_candidate_from_snapshot(market=market, snapshot=snapshot),
                score=snapshot.score,
                price_delta=snapshot.price_delta,
                price_delta_pct=snapshot.price_delta_pct,
                value_per_wallet=snapshot.value_per_wallet,
            )
            for market, snapshot in rows
        ],
    )


def list_latest_qualified_markets() -> QualifiedMarketResult:
    latest_run_id = get_latest_qualified_market_run_id()
    if latest_run_id is None:
        return QualifiedMarketResult(
            profiles=[WhaleQualifiedMarketProfile(name="high_value")],
            qualified_markets=[],
        )

    return list_qualified_markets(latest_run_id)


def _upsert_qualified_markets(
    *,
    session: Session,
    markets: list[QualifiedMarket],
    seen_at: datetime,
) -> dict[str, int]:
    rows = [
        _market_identity_row(candidate=market.candidate, seen_at=seen_at)
        for market in markets
    ]
    if not rows:
        return {}

    statement = insert(QualifiedMarketIdentity).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"token_id", "first_seen_at"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[QualifiedMarketIdentity.token_id],
            set_=update_columns,
        )
    )
    return dict(
        session.execute(
            select(QualifiedMarketIdentity.token_id, QualifiedMarketIdentity.id).where(
                QualifiedMarketIdentity.token_id.in_(
                    [row["token_id"] for row in rows]
                )
            )
        ).all()
    )


def _upsert_metric_snapshots(
    *,
    session: Session,
    markets: list[QualifiedMarket],
    run_id: str,
    generated_at: datetime,
    identity_ids: dict[str, int],
) -> None:
    rows = [
        _metric_snapshot_row(
            market=market,
            run_id=run_id,
            rank=index,
            generated_at=generated_at,
            identity_id=identity_ids[market.candidate.token_id],
        )
        for index, market in enumerate(markets, start=1)
    ]
    if not rows:
        return

    statement = insert(QualifiedMarketMetricSnapshot).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "identity_id", "profile_name"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                QualifiedMarketMetricSnapshot.run_id,
                QualifiedMarketMetricSnapshot.identity_id,
                QualifiedMarketMetricSnapshot.profile_name,
            ],
            set_=update_columns,
        )
    )


def _market_identity_row(
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
        "opposite_token_id": candidate.opposite_token_id,
        "opposite_outcome": candidate.opposite_outcome,
        "end_date": candidate.end_date,
        "negative_risk": candidate.negative_risk,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
    }


def _metric_snapshot_row(
    *,
    market: QualifiedMarket,
    run_id: str,
    rank: int,
    generated_at: datetime,
    identity_id: int,
) -> dict:
    return {
        "run_id": run_id,
        "identity_id": identity_id,
        "profile_name": market.profile,
        "rank": rank,
        "score": market.score,
        "price_delta": market.price_delta,
        "price_delta_pct": market.price_delta_pct,
        "value_per_wallet": market.value_per_wallet,
        "candidate": market.candidate.model_dump(mode="json"),
        "generated_at": generated_at,
    }


def _candidate_from_snapshot(
    *,
    market: QualifiedMarketIdentity,
    snapshot: QualifiedMarketMetricSnapshot,
) -> MarketCandidate:
    candidate = dict(snapshot.candidate)
    candidate.update(
        {
            "token_id": market.token_id,
            "condition_id": market.condition_id,
            "title": market.title,
            "slug": market.slug,
            "outcome": market.outcome,
            "opposite_token_id": market.opposite_token_id,
            "opposite_outcome": market.opposite_outcome,
            "end_date": market.end_date,
            "negative_risk": market.negative_risk,
        }
    )
    return MarketCandidate.model_validate(candidate)


def qualified_config_key(
    *,
    profiles: Sequence[WhaleQualifiedMarketProfile],
    limit: int | None,
) -> str:
    return json.dumps(
        {
            "profiles": [
                profile.model_dump(mode="json")
                for profile in sorted(profiles, key=lambda item: item.name)
            ],
            "limit": limit,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
