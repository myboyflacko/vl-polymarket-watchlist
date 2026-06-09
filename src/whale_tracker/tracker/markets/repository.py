from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from whale_tracker.core.db.engine import database_session
from whale_tracker.core.time import ensure_utc
from whale_tracker.tracker.markets.domain import (
    FilteredMarkets,
    Market,
    MarketRunSummary,
    MarketSnapshot,
    ScoredMarket,
    ScoredMarkets,
    TrackedMarket,
    TrackedMarkets,
)
from whale_tracker.tracker.markets.filter import DefaultTrackedMarketFilterProfile
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    MarketMetricSnapshot,
    MarketRun,
    TrackedMarketMetric,
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
    filtered_markets: FilteredMarkets,
    scored_markets: ScoredMarkets | None,
    limit: int | None = None,
) -> None:
    generated_at = ensure_utc(generated_at)
    snapshot_entries = _snapshot_entries(
        filtered_markets=filtered_markets,
        scored_markets=scored_markets,
    )
    removed_market_count = (
        filtered_markets.removed_market_count
        + (scored_markets.removed_market_count if scored_markets is not None else 0)
    )

    with database_session() as session:
        session.add(
            MarketRun(
                run_id=run_id,
                whales_run_id=whales_run_id,
                status="completed",
                generated_at=generated_at,
                filter_profile=filtered_markets.profile_name,
                scoring_profile=(
                    scored_markets.profile_name if scored_markets is not None else ""
                ),
                checked_market_count=filtered_markets.checked_market_count,
                filtered_market_count=filtered_markets.market_count,
                scored_market_count=len(snapshot_entries),
                removed_market_count=removed_market_count,
                limit=limit,
            )
        )
        market_ids = _upsert_markets(
            markets=[entry.market for entry in snapshot_entries],
            seen_at=generated_at,
            session=session,
        )
        _upsert_metric_snapshots(
            entries=snapshot_entries,
            run_id=run_id,
            generated_at=generated_at,
            session=session,
            market_ids=market_ids,
        )
        session.commit()


def get_latest_tracked_market_run_id() -> str | None:
    with database_session() as session:
        run_id = session.scalar(
            select(TrackedMarketMetric.run_id)
            .join(MarketRun, MarketRun.run_id == TrackedMarketMetric.run_id)
            .order_by(MarketRun.generated_at.desc(), TrackedMarketMetric.run_id.desc())
            .limit(1)
        )

    return run_id


def list_tracked_markets(run_id: str | None = None) -> TrackedMarkets:
    actual_run_id = run_id or get_latest_tracked_market_run_id()
    if actual_run_id is None:
        return _empty_tracked_markets(run_id="")

    with database_session() as session:
        run = session.get(MarketRun, actual_run_id)
        if run is None:
            return _empty_tracked_markets(run_id=actual_run_id)

        rows = list(
            session.execute(
                select(MarketIdentity, TrackedMarketMetric)
                .join(
                    TrackedMarketMetric,
                    TrackedMarketMetric.market_id == MarketIdentity.id,
                )
                .where(TrackedMarketMetric.run_id == actual_run_id)
                .order_by(TrackedMarketMetric.id)
            )
        )

        markets = [
            _tracked_market_from_snapshot(run=run, market=market, snapshot=snapshot)
            for market, snapshot in rows
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


def persist_tracked_markets(
    *,
    run_id: str,
    filter_profile: DefaultTrackedMarketFilterProfile | None = None,
) -> TrackedMarkets:
    profile = filter_profile or DefaultTrackedMarketFilterProfile()
    with database_session() as session:
        run = session.get(MarketRun, run_id)
        if run is None:
            raise ValueError(f"Market run not found: {run_id}")

        rows = list(
            session.execute(
                select(MarketIdentity, MarketMetricSnapshot)
                .join(
                    MarketMetricSnapshot,
                    MarketMetricSnapshot.market_id == MarketIdentity.id,
                )
                .where(MarketMetricSnapshot.run_id == run_id)
                .order_by(MarketMetricSnapshot.id)
            )
        )
        candidates = [
            _market_from_snapshot(market=market, snapshot=snapshot)
            for market, snapshot in rows
        ]
        tracked_markets = profile.run(candidates)
        market_ids = {market.token_id: market.id for market, _snapshot in rows}
        insert_rows = [
            {
                "run_id": run_id,
                "market_id": market_ids[market.token_id],
                "filter_profile": profile.name,
                "metrics": _metrics_payload(market),
                "generated_at": ensure_utc(run.generated_at),
            }
            for market in tracked_markets
            if market.token_id in market_ids
        ]
        if insert_rows:
            statement = insert(TrackedMarketMetric).values(insert_rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        TrackedMarketMetric.run_id,
                        TrackedMarketMetric.market_id,
                        TrackedMarketMetric.filter_profile,
                    ],
                    set_={
                        "metrics": statement.excluded.metrics,
                        "generated_at": statement.excluded.generated_at,
                    },
                )
            )

        session.commit()

    return list_tracked_markets(run_id)


def list_markets(
    *,
    run_id: str | None = None,
    limit: int | None = None,
) -> list[Market]:
    actual_run_id = run_id or get_latest_market_run_id()
    if actual_run_id is None:
        return []

    rows = _market_rows(run_id=actual_run_id, limit=limit)
    return [_market_from_snapshot(market=market, snapshot=snapshot) for market, snapshot in rows]


def list_qualified_markets(
    *,
    run_id: str | None = None,
    limit: int | None = None,
) -> list[Market]:
    return list_markets(run_id=run_id, limit=limit)


def list_market_snapshots(
    token_id: str,
    *,
    limit: int | None = None,
) -> list[MarketSnapshot]:
    with database_session() as session:
        statement = (
            select(MarketIdentity, MarketMetricSnapshot)
            .join(MarketMetricSnapshot, MarketMetricSnapshot.market_id == MarketIdentity.id)
            .where(MarketIdentity.token_id == token_id)
            .order_by(
                MarketMetricSnapshot.generated_at.desc(),
                MarketMetricSnapshot.run_id.desc(),
            )
        )
        if limit is not None:
            statement = statement.limit(limit)

        rows = session.execute(statement).all()

    return [
        MarketSnapshot(
            **_market_from_snapshot(market=market, snapshot=snapshot).model_dump(),
            run_id=snapshot.run_id,
            generated_at=snapshot.generated_at,
        )
        for market, snapshot in rows
    ]


def _snapshot_entries(
    *,
    filtered_markets: FilteredMarkets,
    scored_markets: ScoredMarkets | None,
) -> list[ScoredMarket]:
    if scored_markets is not None:
        return scored_markets.markets

    return [
        ScoredMarket(market=market, score=0.0)
        for market in filtered_markets.markets
    ]


def _market_rows(*, run_id: str, limit: int | None):
    with database_session() as session:
        statement = (
            select(MarketIdentity, MarketMetricSnapshot)
            .join(MarketMetricSnapshot, MarketMetricSnapshot.market_id == MarketIdentity.id)
            .where(MarketMetricSnapshot.run_id == run_id)
            .order_by(MarketMetricSnapshot.score.desc(), MarketMetricSnapshot.id)
        )
        if limit is not None:
            statement = statement.limit(limit)

        return session.execute(statement).all()


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
        filtered_market_count=run.filtered_market_count,
        scored_market_count=run.scored_market_count,
        removed_market_count=run.removed_market_count,
        limit=run.limit,
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


def _upsert_metric_snapshots(
    *,
    entries: list[ScoredMarket],
    run_id: str,
    generated_at: datetime,
    session,
    market_ids: dict[str, int],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "market_id": market_ids[entry.market.token_id],
            "score": entry.score,
            "metrics": _metrics_payload(entry.market),
            "generated_at": generated_at,
        }
        for entry in entries
        if entry.market.token_id in market_ids
    ]
    if not rows:
        return

    statement = insert(MarketMetricSnapshot).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "market_id"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                MarketMetricSnapshot.run_id,
                MarketMetricSnapshot.market_id,
            ],
            set_=update_columns,
        )
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


def _metrics_payload(market: Market) -> dict:
    return {
        "whale_count": market.whale_count,
        "wallets": market.wallets,
        "total_size": market.total_size,
        "total_current_value": market.total_current_value,
        "weighted_avg_price": market.weighted_avg_price,
        "cur_price": market.cur_price,
        "negative_risk": market.negative_risk,
        "qualified": market.qualified,
        "categories": market.categories,
        "category_scores": market.category_scores,
        "price_delta": market.price_delta,
        "price_delta_pct": market.price_delta_pct,
        "value_per_wallet": market.value_per_wallet,
    }


def _market_from_snapshot(
    *,
    market: MarketIdentity,
    snapshot: MarketMetricSnapshot,
) -> Market:
    metrics = dict(snapshot.metrics)
    return Market(
        token_id=market.token_id,
        condition_id=market.condition_id,
        title=market.title,
        slug=market.slug,
        outcome=market.outcome,
        whale_count=metrics.get("whale_count", 0),
        wallets=list(metrics.get("wallets", [])),
        total_size=metrics.get("total_size", 0.0),
        total_current_value=metrics.get("total_current_value", 0.0),
        weighted_avg_price=metrics.get("weighted_avg_price", 0.0),
        cur_price=metrics.get("cur_price", 0.0),
        opposite_token_id=market.opposite_token_id,
        opposite_outcome=market.opposite_outcome,
        end_date=market.end_date,
        negative_risk=metrics.get("negative_risk", False),
        qualified=bool(metrics.get("qualified", False)),
        categories=list(metrics.get("categories", [])),
        category_scores=dict(metrics.get("category_scores", {})),
        score=snapshot.score,
        price_delta=metrics.get("price_delta", 0.0),
        price_delta_pct=metrics.get("price_delta_pct"),
        value_per_wallet=metrics.get("value_per_wallet", 0.0),
    )


def _tracked_market_from_snapshot(
    *,
    run: MarketRun,
    market: MarketIdentity,
    snapshot: TrackedMarketMetric,
) -> TrackedMarket:
    metrics = dict(snapshot.metrics)
    return TrackedMarket(
        token_id=market.token_id,
        condition_id=market.condition_id,
        title=market.title,
        slug=market.slug,
        outcome=market.outcome,
        whale_count=metrics.get("whale_count", 0),
        wallets=list(metrics.get("wallets", [])),
        total_size=metrics.get("total_size", 0.0),
        total_current_value=metrics.get("total_current_value", 0.0),
        weighted_avg_price=metrics.get("weighted_avg_price", 0.0),
        cur_price=metrics.get("cur_price", 0.0),
        opposite_token_id=market.opposite_token_id,
        opposite_outcome=market.opposite_outcome,
        end_date=market.end_date,
        negative_risk=metrics.get("negative_risk", False),
        qualified=bool(metrics.get("qualified", False)),
        categories=list(metrics.get("categories", [])),
        category_scores=dict(metrics.get("category_scores", {})),
        score=0.0,
        price_delta=metrics.get("price_delta", 0.0),
        price_delta_pct=metrics.get("price_delta_pct"),
        value_per_wallet=metrics.get("value_per_wallet", 0.0),
        run_id=run.run_id,
        whales_run_id=run.whales_run_id,
        generated_at=snapshot.generated_at,
        filter_profile=snapshot.filter_profile,
    )
