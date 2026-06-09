from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from whale_tracker.core.db.engine import database_session
from whale_tracker.core.time import ensure_utc
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
    TrackedMarket as TrackedMarketRow,
)
from whale_tracker.tracker.orderbooks.domain import (
    OrderBookLevel,
    OrderBookSnapshot,
    TrackedMarketOrderBookSource,
    TrackedOrderBook,
    TrackedOrderBooks,
)
from whale_tracker.tracker.orderbooks.models import (
    OrderBookMetric,
    OrderBookRun,
)


def get_latest_orderbook_run_id() -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(OrderBookRun)
            .where(OrderBookRun.status == "completed")
            .order_by(OrderBookRun.generated_at.desc(), OrderBookRun.run_id.desc())
            .limit(1)
        )

    return run.run_id if run is not None else None


def list_tracked_market_sources(*, market_run_id: str) -> list[TrackedMarketOrderBookSource]:
    with database_session() as session:
        rows = list(
            session.execute(
                select(TrackedMarketRow, MarketIdentity)
                .join(MarketIdentity, TrackedMarketRow.market_id == MarketIdentity.id)
                .where(TrackedMarketRow.run_id == market_run_id)
                .order_by(TrackedMarketRow.id)
            )
        )

    return [
        TrackedMarketOrderBookSource(
            tracked_market_id=tracked.id,
            token_id=market.token_id,
            condition_id=market.condition_id,
            title=market.title,
            slug=market.slug,
            outcome=market.outcome,
        )
        for tracked, market in rows
    ]


def persist_orderbook_run(
    *,
    run_id: str,
    market_run_id: str,
    generated_at: datetime,
    depth: int,
    checked_market_count: int,
) -> None:
    generated_at = ensure_utc(generated_at)
    with database_session() as session:
        session.add(
            OrderBookRun(
                run_id=run_id,
                market_run_id=market_run_id,
                status="completed",
                generated_at=generated_at,
                depth=depth,
                checked_market_count=checked_market_count,
                stored_orderbook_count=0,
                failed_orderbook_count=0,
            )
        )
        session.commit()


def persist_orderbook_metrics(
    *,
    run_id: str,
    snapshots: list[OrderBookSnapshot],
    failed_orderbook_count: int,
) -> TrackedOrderBooks:
    with database_session() as session:
        run = session.get(OrderBookRun, run_id)
        if run is None:
            raise ValueError(f"Orderbook run not found: {run_id}")

        rows = [_metric_row(run_id=run_id, snapshot=snapshot) for snapshot in snapshots]
        if rows:
            statement = insert(OrderBookMetric).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        OrderBookMetric.run_id,
                        OrderBookMetric.tracked_market_id,
                    ],
                    set_={
                        "exchange_timestamp": statement.excluded.exchange_timestamp,
                        "exchange_timestamp_raw": statement.excluded.exchange_timestamp_raw,
                        "book_hash": statement.excluded.book_hash,
                        "bids": statement.excluded.bids,
                        "asks": statement.excluded.asks,
                        "best_bid": statement.excluded.best_bid,
                        "best_ask": statement.excluded.best_ask,
                        "spread": statement.excluded.spread,
                        "midpoint": statement.excluded.midpoint,
                        "min_order_size": statement.excluded.min_order_size,
                        "tick_size": statement.excluded.tick_size,
                        "negative_risk": statement.excluded.negative_risk,
                        "last_trade_price": statement.excluded.last_trade_price,
                        "generated_at": statement.excluded.generated_at,
                    },
                )
            )

        session.execute(
            update(OrderBookRun)
            .where(OrderBookRun.run_id == run_id)
            .values(
                stored_orderbook_count=len(rows),
                failed_orderbook_count=failed_orderbook_count,
            )
        )
        session.commit()

    return list_tracked_orderbooks(run_id=run_id)


def list_tracked_orderbooks(*, run_id: str | None = None) -> TrackedOrderBooks:
    actual_run_id = run_id or get_latest_orderbook_run_id()
    if actual_run_id is None:
        return _empty_tracked_orderbooks(run_id="", market_run_id="")

    with database_session() as session:
        run = session.get(OrderBookRun, actual_run_id)
        if run is None:
            return _empty_tracked_orderbooks(run_id=actual_run_id, market_run_id="")

        rows = list(
            session.execute(
                select(OrderBookMetric, TrackedMarketRow, MarketIdentity)
                .join(
                    TrackedMarketRow,
                    OrderBookMetric.tracked_market_id == TrackedMarketRow.id,
                )
                .join(MarketIdentity, TrackedMarketRow.market_id == MarketIdentity.id)
                .where(OrderBookMetric.run_id == actual_run_id)
                .order_by(OrderBookMetric.id)
            )
        )

    orderbooks = [
        _tracked_orderbook_from_row(run=run, row=row, market=market)
        for row, _tracked, market in rows
    ]
    return TrackedOrderBooks(
        orderbooks=orderbooks,
        run_id=run.run_id,
        market_run_id=run.market_run_id,
        generated_at=run.generated_at,
        depth=run.depth,
    )


def _empty_tracked_orderbooks(*, run_id: str, market_run_id: str) -> TrackedOrderBooks:
    return TrackedOrderBooks(
        orderbooks=[],
        run_id=run_id,
        market_run_id=market_run_id,
        generated_at=datetime.min.replace(tzinfo=UTC),
        depth=5,
    )


def _metric_row(*, run_id: str, snapshot: OrderBookSnapshot) -> dict:
    return {
        "run_id": run_id,
        "tracked_market_id": snapshot.tracked_market_id,
        "exchange_timestamp": snapshot.exchange_timestamp,
        "exchange_timestamp_raw": snapshot.exchange_timestamp_raw,
        "book_hash": snapshot.book_hash,
        "bids": [level.model_dump() for level in snapshot.bids],
        "asks": [level.model_dump() for level in snapshot.asks],
        "best_bid": snapshot.best_bid,
        "best_ask": snapshot.best_ask,
        "spread": snapshot.spread,
        "midpoint": snapshot.midpoint,
        "min_order_size": snapshot.min_order_size,
        "tick_size": snapshot.tick_size,
        "negative_risk": snapshot.negative_risk,
        "last_trade_price": snapshot.last_trade_price,
        "generated_at": ensure_utc(snapshot.generated_at),
    }


def _tracked_orderbook_from_row(
    *,
    run: OrderBookRun,
    row: OrderBookMetric,
    market: MarketIdentity,
) -> TrackedOrderBook:
    bids = [OrderBookLevel(**level) for level in row.bids]
    asks = [OrderBookLevel(**level) for level in row.asks]
    return TrackedOrderBook(
        run_id=run.run_id,
        market_run_id=run.market_run_id,
        tracked_market_id=row.tracked_market_id,
        token_id=market.token_id,
        condition_id=market.condition_id,
        market=market.condition_id,
        exchange_timestamp=row.exchange_timestamp,
        exchange_timestamp_raw=row.exchange_timestamp_raw,
        book_hash=row.book_hash,
        bids=bids,
        asks=asks,
        best_bid=row.best_bid,
        best_ask=row.best_ask,
        spread=row.spread,
        midpoint=row.midpoint,
        min_order_size=row.min_order_size,
        tick_size=row.tick_size,
        negative_risk=row.negative_risk,
        last_trade_price=row.last_trade_price,
        generated_at=row.generated_at,
    )
