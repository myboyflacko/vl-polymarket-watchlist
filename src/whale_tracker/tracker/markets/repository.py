from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from whale_tracker.core.db.engine import database_session
from whale_tracker.core.time import ensure_utc
from whale_tracker.tracker.markets.domain import (
    MarketObservation,
    MarketRunSummary,
    TrackedMarket,
    TrackedMarkets,
)
from whale_tracker.tracker.markets.filter import TrackedMarketFilterProfile
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    MarketObservation as MarketObservationRow,
    MarketRun,
)


DEFAULT_TRACKED_MARKET_FILTER_PROFILE = "dominant_side_5_whales_80_percent_latest_run"


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
            )
        )
        session.commit()


def persist_market_observations(
    *,
    run_id: str,
    generated_at: datetime,
    observations: list[MarketObservation],
    filter_profile: TrackedMarketFilterProfile | None = None,
) -> TrackedMarkets:
    generated_at = ensure_utc(generated_at)

    with database_session() as session:
        run = session.get(MarketRun, run_id)
        if run is None:
            raise ValueError(f"Market run not found: {run_id}")

        market_ids = _upsert_markets(
            observations=observations,
            seen_at=generated_at,
            session=session,
        )
        rows = [
            {
                "run_id": run_id,
                "market_id": market_ids[observation.token_id],
                "wallet": observation.proxy_wallet,
                "size": observation.size,
                "current_value": observation.current_value,
                "avg_price": observation.avg_price,
                "cur_price": observation.cur_price,
                "negative_risk": observation.negative_risk,
                "generated_at": generated_at,
            }
            for observation in observations
            if observation.token_id in market_ids
        ]
        if rows:
            statement = insert(MarketObservationRow).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        MarketObservationRow.run_id,
                        MarketObservationRow.wallet,
                        MarketObservationRow.market_id,
                    ],
                    set_={
                        "size": statement.excluded.size,
                        "current_value": statement.excluded.current_value,
                        "avg_price": statement.excluded.avg_price,
                        "cur_price": statement.excluded.cur_price,
                        "negative_risk": statement.excluded.negative_risk,
                        "generated_at": statement.excluded.generated_at,
                    },
                )
            )

        session.commit()

    return list_tracked_markets(run_id, filter_profile=filter_profile)


def list_tracked_markets(
    run_id: str | None = None,
    *,
    filter_profile: TrackedMarketFilterProfile | None = None,
) -> TrackedMarkets:
    actual_run_id = run_id or get_latest_market_run_id()
    if actual_run_id is None:
        return _empty_tracked_markets(run_id="")

    with database_session() as session:
        run = session.get(MarketRun, actual_run_id)
        if run is None:
            return _empty_tracked_markets(run_id=actual_run_id)

        rows = [
            _observation_from_row(row=row, market=market)
            for row, market in session.execute(
                select(MarketObservationRow, MarketIdentity)
                .join(
                    MarketIdentity,
                    MarketObservationRow.market_id == MarketIdentity.id,
                )
                .where(MarketObservationRow.run_id == actual_run_id)
                .order_by(MarketObservationRow.id)
            )
        ]

    actual_filter_profile = filter_profile or TrackedMarketFilterProfile()
    markets = [
        _tracked_market_from_market(
            run=run,
            market=market,
            generated_at=run.generated_at,
            filter_profile=actual_filter_profile.name,
        )
        for market in actual_filter_profile.run_observations(rows)
    ]
    return TrackedMarkets(
        markets=markets,
        run_id=actual_run_id,
        whales_run_id=run.whales_run_id,
        generated_at=run.generated_at,
        filter_profile=actual_filter_profile.name,
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
    )


def _empty_tracked_markets(*, run_id: str) -> TrackedMarkets:
    return TrackedMarkets(
        markets=[],
        run_id=run_id,
        generated_at=datetime.min.replace(tzinfo=UTC),
        filter_profile=DEFAULT_TRACKED_MARKET_FILTER_PROFILE,
    )


def _upsert_markets(
    *,
    observations: list[MarketObservation],
    seen_at: datetime,
    session,
) -> dict[str, int]:
    rows_by_token = {
        observation.token_id: _market_row(observation=observation, seen_at=seen_at)
        for observation in observations
    }
    rows = list(rows_by_token.values())
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


def _market_row(*, observation: MarketObservation, seen_at: datetime) -> dict:
    return {
        "token_id": observation.token_id,
        "condition_id": observation.condition_id,
        "title": observation.title,
        "slug": observation.slug,
        "outcome": observation.outcome,
        "opposite_token_id": observation.opposite_token_id,
        "opposite_outcome": observation.opposite_outcome,
        "end_date": observation.end_date,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
    }


def _observation_from_row(
    *,
    row: MarketObservationRow,
    market: MarketIdentity,
) -> MarketObservation:
    return MarketObservation(
        proxy_wallet=row.wallet,
        token_id=market.token_id,
        condition_id=market.condition_id,
        title=market.title,
        slug=market.slug,
        outcome=market.outcome,
        size=row.size,
        current_value=row.current_value,
        avg_price=row.avg_price,
        cur_price=row.cur_price,
        opposite_token_id=market.opposite_token_id,
        opposite_outcome=market.opposite_outcome,
        end_date=market.end_date,
        negative_risk=row.negative_risk,
        generated_at=row.generated_at,
    )


def _tracked_market_from_market(
    *,
    run: MarketRun,
    market,
    generated_at: datetime,
    filter_profile: str,
) -> TrackedMarket:
    return TrackedMarket(
        token_id=market.token_id,
        condition_id=market.condition_id,
        title=market.title,
        slug=market.slug,
        outcome=market.outcome,
        whale_count=market.whale_count,
        wallets=market.wallets,
        total_size=market.total_size,
        total_current_value=market.total_current_value,
        weighted_avg_price=market.weighted_avg_price,
        cur_price=market.cur_price,
        opposite_token_id=market.opposite_token_id,
        opposite_outcome=market.opposite_outcome,
        end_date=market.end_date,
        negative_risk=market.negative_risk,
        run_id=run.run_id,
        whales_run_id=run.whales_run_id,
        generated_at=generated_at,
        filter_profile=filter_profile,
    )
