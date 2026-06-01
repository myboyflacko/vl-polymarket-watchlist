from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from void_liquidity.data.base import Base
from void_liquidity.adapters.polymarket.markets.whales.selection import (
    models as _selection_models,
)


_ = _selection_models


class WhaleMarketCandidateRun(Base):
    __tablename__ = "polymarket_whale_market_candidate_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    selection_run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_selection_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    min_whale_count: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshots: Mapped[list["WhaleMarketMetricSnapshot"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="WhaleMarketMetricSnapshot.id",
    )


class WhaleMarket(Base):
    __tablename__ = "polymarket_whale_markets"
    __table_args__ = (
        Index("ix_whale_markets_condition_id", "condition_id"),
        Index("ix_whale_markets_end_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    opposite_token_id: Mapped[str | None] = mapped_column(String, nullable=True)
    opposite_outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    negative_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    snapshots: Mapped[list["WhaleMarketMetricSnapshot"]] = relationship(
        back_populates="market",
        cascade="all, delete-orphan",
        order_by="WhaleMarketMetricSnapshot.id",
    )


class WhaleMarketMetricSnapshot(Base):
    __tablename__ = "polymarket_whale_market_metric_snapshots"
    __table_args__ = (
        Index(
            "ux_whale_market_metric_snapshots_run_token",
            "run_id",
            "token_id",
            unique=True,
        ),
        Index("ix_whale_market_metric_snapshots_token_id", "token_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_market_candidate_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_markets.token_id", ondelete="CASCADE"),
        nullable=False,
    )
    whale_count: Mapped[int] = mapped_column(Integer, nullable=False)
    wallets: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    total_size: Mapped[float] = mapped_column(Float, nullable=False)
    total_current_value: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    cur_price: Mapped[float] = mapped_column(Float, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[WhaleMarketCandidateRun] = relationship(back_populates="snapshots")
    market: Mapped[WhaleMarket] = relationship(back_populates="snapshots")
