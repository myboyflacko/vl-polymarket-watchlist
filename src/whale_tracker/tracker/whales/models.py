from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whale_tracker.core.db.base import Base


class WhaleRun(Base):
    __tablename__ = "polymarket_whale_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    profile_version: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    filter_profile: Mapped[str] = mapped_column(String, nullable=False)
    scoring_profile: Mapped[str] = mapped_column(String, nullable=False)

    checked_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filtered_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    metrics: Mapped[list["WhaleMetric"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="WhaleMetric.id",
    )


class PolymarketWhale(Base):
    __tablename__ = "polymarket_whales"
    __table_args__ = (
        Index("ux_polymarket_whales_proxy_wallet", "proxy_wallet", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    identity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
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

    metrics: Mapped[list["WhaleMetric"]] = relationship(
        back_populates="whale",
        cascade="all, delete-orphan",
        order_by="WhaleMetric.id",
    )


class WhaleMetric(Base):
    __tablename__ = "polymarket_whale_metrics"
    __table_args__ = (
        Index(
            "ux_polymarket_whale_metrics_run_whale",
            "run_id",
            "whale_id",
            unique=True,
        ),
        Index("ix_polymarket_whale_metrics_whale_id", "whale_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    whale_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_whales.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[WhaleRun] = relationship(back_populates="metrics")
    whale: Mapped[PolymarketWhale] = relationship(back_populates="metrics", lazy="joined")

    @property
    def proxy_wallet(self) -> str:
        return self.whale.proxy_wallet


class TrackedWhaleMetric(Base):
    __tablename__ = "polymarket_tracked_whales"
    __table_args__ = (
        Index(
            "ux_polymarket_tracked_whales_run_whale_filter",
            "run_id",
            "whale_id",
            "filter_profile",
            unique=True,
        ),
        Index("ix_polymarket_tracked_whales_run_id", "run_id"),
        Index("ix_polymarket_tracked_whales_whale_id", "whale_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    whale_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_whales.id", ondelete="CASCADE"),
        nullable=False,
    )
    filter_profile: Mapped[str] = mapped_column(String, nullable=False)
    consecutive_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    whale: Mapped[PolymarketWhale] = relationship(lazy="joined")
