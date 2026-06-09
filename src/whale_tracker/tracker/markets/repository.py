from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from whale_tracker.core.db.engine import database_session
from whale_tracker.core.time import ensure_utc
from whale_tracker.tracker.markets.domain import (
    Market,
    MarketRunSummary,
    TrackedMarket,
    TrackedMarkets,
)
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    MarketRun,
    TrackedMarket as TrackedMarketRow,
)


DEFAULT_TRACKED_MARKET_FILTER_PROFILE = "same_side_3_whales_unique_condition_v1"


def get_latest_market_run() -> MarketRunSummary | None:
    with database_session() as session:
        run = session.scalar(_latest_run_statement())

    return _run_summary(run) if run is not None else None


def get_latest_market_run_id() -> str | None:
    run = get_latest_market_run()
    return run.run_id if run is not None else None


def persist_market_run(
    *,
    run_id: str,
    whales_run_id: str | None,
    generated_at: datetime,
    checked_market_count: int,
) -> None:
    generated_at = ensure_utc(generated_at)

    with database_session() as session:
        session.add(
            MarketRun(
                run_id=run_id,
                whales_run_id=whales_run_id,
                status="completed",
                generated_at=generated_at,
                checked_market_count=checked_market_count,
                tracked_market_count=0,
            )
        )
        session.commit()


def persist_tracked_markets(
    *,
    run_id: str,
    whales_run_id: str | None,
    generated_at: datetime,
    markets: list[Market],
    filter_profile: str = DEFAULT_TRACKED_MARKET_FILTER_PROFILE,
) -> TrackedMarkets:
    generated_at = ensure_utc(generated_at)
    with database_session() as session:
        run = session.get(MarketRun, run_id)
        if run is None:
            raise ValueError(f"Market run not found: {run_id}")

        market_ids = _upsert_markets(
            markets=markets,
            seen_at=generated_at,
            session=session,
        )
        rows = [
            {
                "run_id": run_id,
                "market_id": market_ids[market.token_id],
                "filter_profile": filter_profile,
                "whale_count": market.whale_count,
                "wallets": market.wallets,
                "total_size": market.total_size,
                "total_current_value": market.total_current_value,
                "weighted_avg_price": market.weighted_avg_price,
                "cur_price": market.cur_price,
                "negative_risk": market.negative_risk,
                "generated_at": generated_at,
            }
            for market in markets
            if market.token_id in market_ids
        ]
        if rows:
            statement = insert(TrackedMarketRow).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        TrackedMarketRow.run_id,
                        TrackedMarketRow.market_id,
                        TrackedMarketRow.filter_profile,
                    ],
                    set_={
                        "whale_count": statement.excluded.whale_count,
                        "wallets": statement.excluded.wallets,
                        "total_size": statement.excluded.total_size,
                        "total_current_value": statement.excluded.total_current_value,
                        "weighted_avg_price": statement.excluded.weighted_avg_price,
                        "cur_price": statement.excluded.cur_price,
                        "negative_risk": statement.excluded.negative_risk,
                        "generated_at": statement.excluded.generated_at,
                    },
                )
            )

        session.execute(
            update(MarketRun)
            .where(MarketRun.run_id == run_id)
            .values(tracked_market_count=len(rows))
        )
        session.commit()

    return list_tracked_markets(run_id)


def list_tracked_markets(run_id: str | None = None) -> TrackedMarkets:
    actual_run_id = run_id or get_latest_market_run_id()
    if actual_run_id is None:
        return _empty_tracked_markets(run_id="")

    with database_session() as session:
        run = session.get(MarketRun, actual_run_id)
        if run is None:
            return _empty_tracked_markets(run_id=actual_run_id)

        rows = list(
            session.execute(
                select(MarketIdentity, TrackedMarketRow)
                .join(
                    TrackedMarketRow,
                    TrackedMarketRow.market_id == MarketIdentity.id,
                )
                .where(TrackedMarketRow.run_id == actual_run_id)
                .order_by(TrackedMarketRow.id)
            )
        )

    markets = [
        _tracked_market_from_row(run=run, market=market, row=row)
        for market, row in rows
    ]
    filter_profile = (
        markets[0].filter_profile
        if markets
        else DEFAULT_TRACKED_MARKET_FILTER_PROFILE
    )
    return TrackedMarkets(
        markets=markets,
        run_id=actual_run_id,
        whales_run_id=run.whales_run_id,
        generated_at=run.generated_at,
        filter_profile=filter_profile,
    )


def _latest_run_statement():
    return (
        select(MarketRun)
        .where(MarketRun.status == "completed")
        .order_by(
            MarketRun.generated_at.desc(),
            MarketRun.run_id.desc(),
        )
        .limit(1)
    )


def _run_summary(run: MarketRun) -> MarketRunSummary:
    return MarketRunSummary(
        run_id=run.run_id,
        whales_run_id=run.whales_run_id,
        generated_at=run.generated_at,
        checked_market_count=run.checked_market_count,
        tracked_market_count=run.tracked_market_count,
    )


def _empty_tracked_markets(*, run_id: str) -> TrackedMarkets:
    return TrackedMarkets(
        markets=[],
        run_id=run_id,
        generated_at=datetime.min.replace(tzinfo=UTC),
        filter_profile=DEFAULT_TRACKED_MARKET_FILTER_PROFILE,
    )


def _upsert_markets(*, markets: list[Market], seen_at: datetime, session) -> dict[str, int]:
    rows = [_market_row(market=market, seen_at=seen_at) for market in markets]
    if not rows:
        return {}

    statement = insert(MarketIdentity).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"token_id", "first_seen_at"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[MarketIdentity.token_id],
            set_=update_columns,
        )
    )
    return dict(
        session.execute(
            select(MarketIdentity.token_id, MarketIdentity.id).where(
                MarketIdentity.token_id.in_([row["token_id"] for row in rows])
            )
        ).all()
    )


def _market_row(*, market: Market, seen_at: datetime) -> dict:
    return {
        "token_id": market.token_id,
        "condition_id": market.condition_id,
        "title": market.title,
        "slug": market.slug,
        "outcome": market.outcome,
        "opposite_token_id": market.opposite_token_id,
        "opposite_outcome": market.opposite_outcome,
        "end_date": market.end_date,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
    }


def _tracked_market_from_row(
    *,
    run: MarketRun,
    market: MarketIdentity,
    row: TrackedMarketRow,
) -> TrackedMarket:
    return TrackedMarket(
        token_id=market.token_id,
        condition_id=market.condition_id,
        title=market.title,
        slug=market.slug,
        outcome=market.outcome,
        whale_count=row.whale_count,
        wallets=list(row.wallets),
        total_size=row.total_size,
        total_current_value=row.total_current_value,
        weighted_avg_price=row.weighted_avg_price,
        cur_price=row.cur_price,
        opposite_token_id=market.opposite_token_id,
        opposite_outcome=market.opposite_outcome,
        end_date=market.end_date,
        negative_risk=row.negative_risk,
        run_id=run.run_id,
        whales_run_id=run.whales_run_id,
        generated_at=row.generated_at,
        filter_profile=row.filter_profile,
    )
