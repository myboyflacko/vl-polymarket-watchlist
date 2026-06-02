from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whale_tracker.core.db.base import Base
from whale_tracker.tracker.whales import models as _whale_models


_ = _whale_models


class MarketRun(Base):
    __tablename__ = "polymarket_market_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    whales_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("polymarket_whale_runs.run_id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    filter_profile: Mapped[str] = mapped_column(String, nullable=False)
    scoring_profile: Mapped[str] = mapped_column(String, nullable=False)

    checked_market_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filtered_market_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored_market_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed_market_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    snapshots: Mapped[list["MarketMetricSnapshot"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="MarketMetricSnapshot.id",
    )


class MarketIdentity(Base):
    __tablename__ = "polymarket_markets"
    __table_args__ = (
        Index("ux_polymarket_markets_token_id", "token_id", unique=True),
        Index("ix_polymarket_markets_condition_id", "condition_id"),
        Index("ix_polymarket_markets_end_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String, nullable=False)
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    opposite_token_id: Mapped[str | None] = mapped_column(String, nullable=True)
    opposite_outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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
    snapshots: Mapped[list["MarketMetricSnapshot"]] = relationship(
        back_populates="market",
        cascade="all, delete-orphan",
        order_by="MarketMetricSnapshot.id",
    )


class MarketMetricSnapshot(Base):
    __tablename__ = "polymarket_market_metrics"
    __table_args__ = (
        Index(
            "ux_polymarket_market_metrics_run_market",
            "run_id",
            "market_id",
            unique=True,
        ),
        Index("ix_polymarket_market_metrics_market_id", "market_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_market_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    market_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_markets.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[MarketRun] = relationship(back_populates="snapshots")
    market: Mapped[MarketIdentity] = relationship(back_populates="snapshots", lazy="joined")

    @property
    def token_id(self) -> str:
        return self.market.token_id
