from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whale_tracker.core.db.base import Base
from whale_tracker.tracker.markets import models as _market_models
from whale_tracker.tracker.markets.models import MarketIdentity


_ = _market_models


class TradeRun(Base):
    __tablename__ = "polymarket_trade_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    market_run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_market_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stored_trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    items: Mapped[list["TradeRunItem"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="TradeRunItem.id",
    )


class TradeFact(Base):
    __tablename__ = "polymarket_trades"
    __table_args__ = (
        Index("ux_polymarket_trades_trade_key", "trade_key", unique=True),
        Index("ix_polymarket_trades_wallet_condition", "wallet", "condition_id"),
        Index("ix_polymarket_trades_market_id", "market_id"),
        Index("ix_polymarket_trades_trade_timestamp", "trade_timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_key: Mapped[str] = mapped_column(String, nullable=False)
    wallet: Mapped[str] = mapped_column(String, nullable=False)
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    market_id: Mapped[int | None] = mapped_column(
        ForeignKey("polymarket_markets.id", ondelete="SET NULL"),
        nullable=True,
    )
    token_id: Mapped[str | None] = mapped_column(String, nullable=True)
    side: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    size: Mapped[float | None] = mapped_column(Float, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    transaction_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    market: Mapped[MarketIdentity | None] = relationship(lazy="joined")


class TradeRunItem(Base):
    __tablename__ = "polymarket_trade_run_items"
    __table_args__ = (
        Index(
            "ux_polymarket_trade_run_items_run_trade",
            "run_id",
            "trade_id",
            unique=True,
        ),
        Index("ix_polymarket_trade_run_items_trade_id", "trade_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_trade_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_trades.id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[TradeRun] = relationship(back_populates="items")
    trade: Mapped[TradeFact] = relationship(lazy="joined")
