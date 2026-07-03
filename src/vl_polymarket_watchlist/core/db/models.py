from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vl_polymarket_watchlist.core.db.base import Base


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class PolymarketCondition(Base):
    __tablename__ = "polymarket_conditions"

    condition_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    question: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enable_order_book: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_latest_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tokens: Mapped[list["PolymarketToken"]] = relationship(
        back_populates="condition",
        cascade="all, delete-orphan",
    )


class PolymarketToken(Base):
    __tablename__ = "polymarket_tokens"
    __table_args__ = (Index("ix_polymarket_tokens_condition_id", "condition_id"),)

    token_id: Mapped[str] = mapped_column(String, primary_key=True)
    condition_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_conditions.condition_id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opposite_token_id: Mapped[str | None] = mapped_column(String, nullable=True)
    opposite_outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enable_order_book: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    condition: Mapped[PolymarketCondition] = relationship(back_populates="tokens")


class MarketDiscoveryRun(Base):
    __tablename__ = "market_discovery_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    input_refs_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    checked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MarketDiscoveryObservation(Base):
    __tablename__ = "market_discovery_observations"
    __table_args__ = (
        Index("ix_market_discovery_observations_source_observed", "source", "observed_at"),
        Index("ix_market_discovery_observations_token_observed", "token_id", "observed_at"),
        Index(
            "ix_market_discovery_observations_condition_observed",
            "condition_id",
            "observed_at",
        ),
        Index("ix_market_discovery_observations_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("market_discovery_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    token_id: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    event_title: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enable_order_book: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    liquidity: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    last_trade_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    outcome_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    source_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    source_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ManualWatchlistItem(Base):
    __tablename__ = "manual_watchlist_items"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    condition_id: Mapped[str | None] = mapped_column(String, nullable=True)
    token_id: Mapped[str | None] = mapped_column(String, nullable=True)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    collect_orderbook: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    collect_trades: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class MarketExclusion(Base):
    __tablename__ = "market_exclusions"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    condition_id: Mapped[str | None] = mapped_column(String, nullable=True)
    token_id: Mapped[str | None] = mapped_column(String, nullable=True)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)


class OrderbookCollectionRun(Base):
    __tablename__ = "orderbook_collection_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    watchlist_version: Mapped[str] = mapped_column(String, nullable=False)
    selected_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OrderbookCollectionItem(Base):
    __tablename__ = "orderbook_collection_items"
    __table_args__ = (
        Index("ix_orderbook_collection_items_run_id", "run_id"),
        Index("ix_orderbook_collection_items_token_id", "token_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("orderbook_collection_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    token_id: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str | None] = mapped_column(String, nullable=True)
    sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    watchlist_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    days_to_expiry: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    collect_orderbook: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderbookSnapshot(Base):
    __tablename__ = "orderbook_snapshots"
    __table_args__ = (
        Index("ix_orderbook_snapshots_token_generated", "token_id", "generated_at"),
        Index("ix_orderbook_snapshots_condition_generated", "condition_id", "generated_at"),
        Index("ix_orderbook_snapshots_run_id", "run_id"),
        Index("ix_orderbook_snapshots_valid_generated", "valid_orderbook", "generated_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("orderbook_collection_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    token_id: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exchange_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exchange_timestamp_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    best_bid: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    best_ask: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    midpoint: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    spread: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    last_trade_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    bid_depth_top_1: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ask_depth_top_1: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    bid_depth_top_3: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ask_depth_top_3: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    bid_depth_top_5: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ask_depth_top_5: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    bid_levels_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ask_levels_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_order_size: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    negative_risk: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bids: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    asks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    book_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    valid_orderbook: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invalid_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_version: Mapped[str] = mapped_column(String, nullable=False)
    api_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
