from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from whale_tracker.core.db.engine import database_session
from whale_tracker.core.time import ensure_utc
from whale_tracker.tracker.markets.repository import list_tracked_markets
from whale_tracker.tracker.markets.models import (
    MarketIdentity,
)
from whale_tracker.tracker.trades.domain import (
    Trade,
    TrackedTrade,
    TrackedTrades,
    TradeSource,
)
from whale_tracker.tracker.trades.models import (
    TradeFact,
    TradeRun,
    TradeRunItem,
)


MAX_TRADE_FACT_ROWS_PER_BATCH = 1_000
MAX_TRADE_RUN_ITEM_ROWS_PER_BATCH = 5_000
MAX_SELECT_IDS_PER_BATCH = 10_000


def get_latest_trade_run_id() -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(TradeRun)
            .where(TradeRun.status == "completed")
            .order_by(TradeRun.generated_at.desc(), TradeRun.run_id.desc())
            .limit(1)
        )

    return run.run_id if run is not None else None


def list_trade_sources(*, market_run_id: str) -> list[TradeSource]:
    selected_markets = list_tracked_markets(run_id=market_run_id).markets
    token_ids = [
        token_id
        for market in selected_markets
        for token_id in (market.token_id, market.opposite_token_id)
        if token_id is not None
    ]
    if not token_ids:
        return []

    with database_session() as session:
        identities = {
            market.token_id: market
            for market in session.scalars(
                select(MarketIdentity)
                .where(MarketIdentity.token_id.in_(token_ids))
                .order_by(MarketIdentity.id)
            )
        }

    sources_by_key: dict[tuple[str, str], TradeSource] = {}
    for market in selected_markets:
        for wallet in market.wallets:
            key = (wallet, market.condition_id)
            source = sources_by_key.setdefault(
                key,
                TradeSource(proxy_wallet=wallet, condition_id=market.condition_id),
            )
            for token_id in (market.token_id, market.opposite_token_id):
                identity = identities.get(token_id or "")
                if identity is not None:
                    source.market_ids_by_token[token_id or ""] = identity.id

        sources = list(sources_by_key.values())
        _attach_trade_sync_state(session=session, sources=sources)

    return sources


def persist_trade_run(
    *,
    run_id: str,
    market_run_id: str,
    generated_at: datetime,
    checked_source_count: int,
) -> None:
    generated_at = ensure_utc(generated_at)
    with database_session() as session:
        session.add(
            TradeRun(
                run_id=run_id,
                market_run_id=market_run_id,
                status="completed",
                generated_at=generated_at,
                checked_source_count=checked_source_count,
                stored_trade_count=0,
                failed_source_count=0,
            )
        )
        session.commit()


def persist_trades(
    *,
    run_id: str,
    trades: list[Trade],
    failed_source_count: int,
) -> TrackedTrades:
    with database_session() as session:
        run = session.get(TradeRun, run_id)
        if run is None:
            raise ValueError(f"Trade run not found: {run_id}")

        trade_ids = _upsert_trade_facts(session=session, trades=trades)
        item_rows = _deduplicate_run_item_rows(
            [
                {
                    "run_id": run_id,
                    "trade_id": trade_ids[trade.trade_key],
                    "generated_at": ensure_utc(trade.generated_at),
                }
                for trade in trades
                if trade.trade_key in trade_ids
            ]
        )
        if item_rows:
            for batch in _batches(item_rows, MAX_TRADE_RUN_ITEM_ROWS_PER_BATCH):
                statement = insert(TradeRunItem).values(batch)
                session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[TradeRunItem.run_id, TradeRunItem.trade_id],
                        set_={"generated_at": statement.excluded.generated_at},
                    )
                )

        session.execute(
            update(TradeRun)
            .where(TradeRun.run_id == run_id)
            .values(
                stored_trade_count=len(item_rows),
                failed_source_count=failed_source_count,
            )
        )
        session.commit()

    return list_tracked_trades(run_id=run_id)


def list_tracked_trades(*, run_id: str | None = None) -> TrackedTrades:
    actual_run_id = run_id or get_latest_trade_run_id()
    if actual_run_id is None:
        return _empty_tracked_trades(run_id="", market_run_id="")

    with database_session() as session:
        run = session.get(TradeRun, actual_run_id)
        if run is None:
            return _empty_tracked_trades(run_id=actual_run_id, market_run_id="")

        rows = list(
            session.scalars(
                select(TradeFact)
                .join(TradeRunItem, TradeRunItem.trade_id == TradeFact.id)
                .where(TradeRunItem.run_id == actual_run_id)
                .order_by(TradeFact.trade_timestamp, TradeFact.id)
            )
        )

    return TrackedTrades(
        trades=[_tracked_trade_from_row(run=run, row=row) for row in rows],
        run_id=run.run_id,
        market_run_id=run.market_run_id,
        generated_at=run.generated_at,
    )


def _empty_tracked_trades(*, run_id: str, market_run_id: str) -> TrackedTrades:
    return TrackedTrades(
        trades=[],
        run_id=run_id,
        market_run_id=market_run_id,
        generated_at=datetime.min.replace(tzinfo=UTC),
    )


def _upsert_trade_facts(*, session, trades: list[Trade]) -> dict[str, int]:
    rows_by_key = {trade.trade_key: _trade_row(trade=trade) for trade in trades}
    rows = list(rows_by_key.values())
    if not rows:
        return {}

    for batch in _batches(rows, MAX_TRADE_FACT_ROWS_PER_BATCH):
        statement = insert(TradeFact).values(batch)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[TradeFact.trade_key],
                set_={
                    "wallet": statement.excluded.wallet,
                    "condition_id": statement.excluded.condition_id,
                    "market_id": statement.excluded.market_id,
                    "token_id": statement.excluded.token_id,
                    "side": statement.excluded.side,
                    "outcome": statement.excluded.outcome,
                    "price": statement.excluded.price,
                    "size": statement.excluded.size,
                    "value": statement.excluded.value,
                    "trade_timestamp": statement.excluded.trade_timestamp,
                    "transaction_hash": statement.excluded.transaction_hash,
                    "raw_payload": statement.excluded.raw_payload,
                    "last_seen_at": statement.excluded.last_seen_at,
                },
            )
        )

    trade_ids: dict[str, int] = {}
    trade_keys = [row["trade_key"] for row in rows]
    for batch in _batches(trade_keys, MAX_SELECT_IDS_PER_BATCH):
        trade_ids.update(
            session.execute(
                select(TradeFact.trade_key, TradeFact.id).where(
                    TradeFact.trade_key.in_(batch)
                )
            ).all()
        )
    return trade_ids


def _trade_row(*, trade: Trade) -> dict:
    generated_at = ensure_utc(trade.generated_at)
    return {
        "trade_key": trade.trade_key,
        "wallet": trade.proxy_wallet,
        "condition_id": trade.condition_id,
        "market_id": trade.market_id,
        "token_id": trade.token_id,
        "side": trade.side,
        "outcome": trade.outcome,
        "price": trade.price,
        "size": trade.size,
        "value": trade.value,
        "trade_timestamp": trade.trade_timestamp,
        "transaction_hash": trade.transaction_hash,
        "raw_payload": trade.raw_payload,
        "first_seen_at": generated_at,
        "last_seen_at": generated_at,
    }


def _tracked_trade_from_row(*, run: TradeRun, row: TradeFact) -> TrackedTrade:
    return TrackedTrade(
        run_id=run.run_id,
        market_run_id=run.market_run_id,
        proxy_wallet=row.wallet,
        condition_id=row.condition_id,
        trade_key=row.trade_key,
        market_id=row.market_id,
        token_id=row.token_id,
        side=row.side,
        outcome=row.outcome,
        price=row.price,
        size=row.size,
        value=row.value,
        trade_timestamp=row.trade_timestamp,
        transaction_hash=row.transaction_hash,
        raw_payload=dict(row.raw_payload),
        generated_at=row.last_seen_at,
    )


def _attach_trade_sync_state(*, session, sources: list[TradeSource]) -> None:
    if not sources:
        return

    source_keys = [
        (source.proxy_wallet, source.condition_id)
        for source in sources
    ]
    latest_rows = session.execute(
        select(
            TradeFact.wallet,
            TradeFact.condition_id,
            func.max(TradeFact.trade_timestamp),
        )
        .where(
            tuple_(TradeFact.wallet, TradeFact.condition_id).in_(source_keys),
            TradeFact.trade_timestamp.is_not(None),
        )
        .group_by(TradeFact.wallet, TradeFact.condition_id)
    ).all()
    latest_by_source = {
        (wallet, condition_id): latest_timestamp
        for wallet, condition_id, latest_timestamp in latest_rows
        if latest_timestamp is not None
    }
    if not latest_by_source:
        return

    known_key_rows = session.execute(
        select(
            TradeFact.wallet,
            TradeFact.condition_id,
            TradeFact.trade_key,
        ).where(
            tuple_(
                TradeFact.wallet,
                TradeFact.condition_id,
                TradeFact.trade_timestamp,
            ).in_(
                [
                    (wallet, condition_id, latest_timestamp)
                    for (wallet, condition_id), latest_timestamp
                    in latest_by_source.items()
                ]
            )
        )
    ).all()
    known_keys_by_source: dict[tuple[str, str], set[str]] = {}
    for wallet, condition_id, trade_key in known_key_rows:
        known_keys_by_source.setdefault((wallet, condition_id), set()).add(trade_key)

    for source in sources:
        key = (source.proxy_wallet, source.condition_id)
        source.latest_trade_timestamp = latest_by_source.get(key)
        source.known_trade_keys = known_keys_by_source.get(key, set())


def _deduplicate_run_item_rows(rows: list[dict]) -> list[dict]:
    return list(
        {
            (row["run_id"], row["trade_id"]): row
            for row in rows
        }.values()
    )


def _batches[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
