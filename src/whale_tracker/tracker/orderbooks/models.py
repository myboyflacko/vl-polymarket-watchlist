from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whale_tracker.core.db.base import Base
from whale_tracker.tracker.markets import models as _market_models
from whale_tracker.tracker.markets.models import TrackedMarket as TrackedMarketRow


_ = _market_models


class OrderBookRun(Base):
    __tablename__ = "polymarket_orderbook_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    market_run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_market_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    checked_market_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stored_orderbook_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_orderbook_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    metrics: Mapped[list["OrderBookMetric"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="OrderBookMetric.id",
    )


class OrderBookMetric(Base):
    __tablename__ = "polymarket_orderbook_metrics"
    __table_args__ = (
        Index(
            "ux_polymarket_orderbook_metrics_run_tracked_market",
            "run_id",
            "tracked_market_id",
            unique=True,
        ),
        Index("ix_polymarket_orderbook_metrics_run_id", "run_id"),
        Index(
            "ix_polymarket_orderbook_metrics_tracked_market_id",
            "tracked_market_id",
        ),
        Index("ix_polymarket_orderbook_metrics_generated_at", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_orderbook_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    tracked_market_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_tracked_markets.id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    exchange_timestamp_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    book_hash: Mapped[str] = mapped_column(String, nullable=False)
    bids: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    asks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    best_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    midpoint: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_order_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    tick_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_risk: Mapped[bool] = mapped_column(nullable=False, default=False)
    last_trade_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[OrderBookRun] = relationship(back_populates="metrics")
    tracked_market: Mapped[TrackedMarketRow] = relationship(lazy="joined")
