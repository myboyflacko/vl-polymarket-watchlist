from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from void_liquidity.adapters.polymarket.markets.whales.qualified.domain import (
    QualifiedMarket,
    QualifiedMarketResult,
    WhaleQualifiedMarketProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.qualified.models import (
    QualifiedMarketRow,
    QualifiedMarketRun,
)
from void_liquidity.data.engine import database_session


def get_latest_qualified_market_run_id() -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(QualifiedMarketRun)
            .order_by(
                QualifiedMarketRun.generated_at.desc(),
                QualifiedMarketRun.run_id.desc(),
            )
            .limit(1)
        )

    return run.run_id if run is not None else None


def persist_qualified_market_run(
    *,
    profile: WhaleQualifiedMarketProfile,
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
                generated_at=generated_at,
                profile=profile.model_dump(mode="json"),
                qualified_market_count=len(result.qualified_markets),
                limit=limit,
            )
        )
        session.add_all(
            QualifiedMarketRow(
                run_id=run_id,
                token_id=market.candidate.token_id,
                profile_name=market.profile,
                rank=index,
                score=market.score,
                price_delta=market.price_delta,
                price_delta_pct=market.price_delta_pct,
                value_per_wallet=market.value_per_wallet,
                candidate=market.candidate.model_dump(mode="json"),
                generated_at=generated_at,
            )
            for index, market in enumerate(result.qualified_markets, start=1)
        )
        session.commit()


def list_qualified_markets(run_id: str) -> QualifiedMarketResult:
    with database_session() as session:
        run = session.get(QualifiedMarketRun, run_id)
        if run is None:
            return QualifiedMarketResult(
                profile=WhaleQualifiedMarketProfile(name="high_value"),
                qualified_markets=[],
            )
        rows = list(
            session.scalars(
                select(QualifiedMarketRow)
                .where(QualifiedMarketRow.run_id == run_id)
                .order_by(QualifiedMarketRow.rank)
            )
        )

    profile = WhaleQualifiedMarketProfile.model_validate(run.profile)
    return QualifiedMarketResult(
        profile=profile,
        qualified_markets=[
            QualifiedMarket(
                profile=row.profile_name,
                candidate=row.candidate,
                score=row.score,
                price_delta=row.price_delta,
                price_delta_pct=row.price_delta_pct,
                value_per_wallet=row.value_per_wallet,
            )
            for row in rows
        ],
    )


def list_latest_qualified_markets() -> QualifiedMarketResult:
    latest_run_id = get_latest_qualified_market_run_id()
    if latest_run_id is None:
        return QualifiedMarketResult(
            profile=WhaleQualifiedMarketProfile(name="high_value"),
            qualified_markets=[],
        )

    return list_qualified_markets(latest_run_id)
