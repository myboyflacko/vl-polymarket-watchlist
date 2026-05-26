from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from void_liquidity.data import Base


class WhaleTrackerRun(Base):
    __tablename__ = "whale_tracker_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    profile_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    candidate_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    report_path: Mapped[str | None] = mapped_column(String, nullable=True)
    tracked_whales: Mapped[list["TrackedWhale"]] = relationship(
        back_populates="tracker_run",
        cascade="all, delete-orphan",
        order_by="TrackedWhale.id",
    )


class TrackedWhale(Base):
    __tablename__ = "tracked_whales"
    __table_args__ = (
        Index("ix_tracked_whales_proxy_wallet", "proxy_wallet"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("whale_tracker_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    tracker_run: Mapped[WhaleTrackerRun] = relationship(back_populates="tracked_whales")


class TrackedWhaleMetricSnapshot(Base):
    __tablename__ = "tracked_whale_metric_snapshots"
    __table_args__ = (
        Index(
            "ix_tracked_whale_metric_snapshots_run_wallet",
            "run_id",
            "proxy_wallet",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("whale_tracker_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    collection_quality: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
