from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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


class TrackedWhale(Base):
    __tablename__ = "tracked_whales"
    __table_args__ = (
        UniqueConstraint("run_id", "proxy_wallet", name="uq_tracked_whales_run_wallet"),
        Index("ix_tracked_whales_proxy_wallet", "proxy_wallet"),
        Index("ix_tracked_whales_run_source", "run_id", "candidate_pool_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("whale_tracker_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    user_name: Mapped[str | None] = mapped_column(String, nullable=True)
    x_username: Mapped[str | None] = mapped_column(String, nullable=True)
    verified_badge: Mapped[bool] = mapped_column(nullable=False, default=False)
    candidate_pool_source: Mapped[str] = mapped_column(String, nullable=False)
    current_position_value: Mapped[float] = mapped_column(Float, nullable=False)
    closed_positions_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    roi: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity_volume_window: Mapped[float] = mapped_column(Float, nullable=False)
    last_activity_at: Mapped[str | None] = mapped_column(String, nullable=True)
    leaderboard: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    exposure: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    closed_positions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    activity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
