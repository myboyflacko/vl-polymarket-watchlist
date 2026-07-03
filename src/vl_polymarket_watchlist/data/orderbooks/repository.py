from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text, update

from vl_polymarket_watchlist.core.db.engine import database_session
from vl_polymarket_watchlist.core.db.models import (
    OrderbookCollectionItem,
    OrderbookCollectionRun,
    OrderbookSnapshot,
)
from vl_polymarket_watchlist.core.time import ensure_utc
from vl_polymarket_watchlist.data.orderbooks.market import (
    OrderBookCollectionItemPayload,
    ParsedOrderBook,
)


WATCHLIST_VERSION = "polymarket_watchlist_v_mvp"


def create_orderbook_collection_run(
    *,
    run_id: str,
    started_at: datetime,
    config_json: dict,
    watchlist_version: str = WATCHLIST_VERSION,
) -> None:
    started_at = ensure_utc(started_at)
    with database_session() as session:
        session.add(
            OrderbookCollectionRun(
                run_id=run_id,
                started_at=started_at,
                status="running",
                watchlist_version=watchlist_version,
                selected_token_count=0,
                success_count=0,
                failure_count=0,
                config_json=config_json,
            )
        )
        session.commit()


def snapshot_collectable_watchlist(
    *,
    run_id: str,
    selected_at: datetime,
) -> list[OrderBookCollectionItemPayload]:
    selected_at = ensure_utc(selected_at)
    with database_session() as session:
        session.execute(
            text(
                """
                INSERT INTO orderbook_collection_items (
                    run_id,
                    condition_id,
                    token_id,
                    slug,
                    title,
                    outcome,
                    priority,
                    sources,
                    watchlist_reason,
                    days_to_expiry,
                    collect_orderbook,
                    selected_at
                )
                SELECT
                    :run_id,
                    condition_id,
                    token_id,
                    slug,
                    title,
                    outcome,
                    priority,
                    sources,
                    watchlist_reason,
                    days_to_expiry,
                    collect_orderbook,
                    :selected_at
                FROM polymarket_watchlist_v
                WHERE collect_orderbook = true
                """
            ),
            {"run_id": run_id, "selected_at": selected_at},
        )
        session.flush()
        items = [
            _item_payload(row)
            for row in session.query(OrderbookCollectionItem)
            .filter(OrderbookCollectionItem.run_id == run_id)
            .order_by(OrderbookCollectionItem.id)
            .all()
        ]
        session.execute(
            update(OrderbookCollectionRun)
            .where(OrderbookCollectionRun.run_id == run_id)
            .values(selected_token_count=len(items))
        )
        session.commit()

    return items


def persist_orderbook_snapshots(
    *,
    run_id: str,
    snapshots: list[ParsedOrderBook],
) -> None:
    with database_session() as session:
        for snapshot in snapshots:
            session.add(
                OrderbookSnapshot(
                    run_id=run_id,
                    condition_id=snapshot.condition_id,
                    token_id=snapshot.token_id,
                    generated_at=ensure_utc(snapshot.generated_at),
                    exchange_timestamp=snapshot.exchange_timestamp,
                    exchange_timestamp_raw=snapshot.exchange_timestamp_raw,
                    best_bid=snapshot.best_bid,
                    best_ask=snapshot.best_ask,
                    midpoint=snapshot.midpoint,
                    spread=snapshot.spread,
                    last_trade_price=snapshot.last_trade_price,
                    bid_depth_top_1=snapshot.bid_depth_top_1,
                    ask_depth_top_1=snapshot.ask_depth_top_1,
                    bid_depth_top_3=snapshot.bid_depth_top_3,
                    ask_depth_top_3=snapshot.ask_depth_top_3,
                    bid_depth_top_5=snapshot.bid_depth_top_5,
                    ask_depth_top_5=snapshot.ask_depth_top_5,
                    bid_levels_count=snapshot.bid_levels_count,
                    ask_levels_count=snapshot.ask_levels_count,
                    min_order_size=snapshot.min_order_size,
                    tick_size=snapshot.tick_size,
                    negative_risk=snapshot.negative_risk,
                    bids=snapshot.bids,
                    asks=snapshot.asks,
                    book_hash=snapshot.book_hash,
                    valid_orderbook=snapshot.valid_orderbook,
                    invalid_reason=snapshot.invalid_reason,
                    parser_version=snapshot.parser_version,
                    api_status=snapshot.api_status,
                    api_error=snapshot.api_error,
                    raw_payload=snapshot.raw_payload,
                )
            )
        session.commit()


def complete_orderbook_collection_run(
    *,
    run_id: str,
    finished_at: datetime,
    success_count: int,
    failure_count: int,
    error_message: str | None = None,
) -> None:
    status = "completed" if failure_count == 0 else "partial"
    if success_count == 0 and failure_count > 0:
        status = "failed"

    with database_session() as session:
        session.execute(
            update(OrderbookCollectionRun)
            .where(OrderbookCollectionRun.run_id == run_id)
            .values(
                finished_at=ensure_utc(finished_at),
                status=status,
                success_count=success_count,
                failure_count=failure_count,
                error_message=error_message,
            )
        )
        session.commit()


def _item_payload(row: OrderbookCollectionItem) -> OrderBookCollectionItemPayload:
    return OrderBookCollectionItemPayload(
        condition_id=row.condition_id,
        token_id=row.token_id,
        slug=row.slug,
        title=row.title,
        outcome=row.outcome,
        priority=row.priority,
        sources=_sources(row.sources),
        watchlist_reason=row.watchlist_reason,
        days_to_expiry=row.days_to_expiry,
        collect_orderbook=row.collect_orderbook,
        selected_at=row.selected_at,
    )


def _sources(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []

        if isinstance(parsed, list):
            return [str(item) for item in parsed]

    return []
