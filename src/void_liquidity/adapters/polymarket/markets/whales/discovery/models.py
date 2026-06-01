from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from void_liquidity.data.base import Base


class WhaleDiscoveryRun(Base):
    __tablename__ = "polymarket_whale_discovery_runs"

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
    whales: Mapped[list["DiscoveredWhale"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DiscoveredWhale.id",
    )
    metrics: Mapped[list["DiscoveredWhaleMetric"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DiscoveredWhaleMetric.id",
    )


class DiscoveredWhale(Base):
    __tablename__ = "polymarket_discovered_whales"
    __table_args__ = (
        Index("ix_discovered_whales_proxy_wallet", "proxy_wallet"),
        Index(
            "ux_discovered_whales_run_wallet",
            "run_id",
            "proxy_wallet",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_discovery_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    identity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[WhaleDiscoveryRun] = relationship(back_populates="whales")


class DiscoveredWhaleMetric(Base):
    __tablename__ = "polymarket_discovered_whale_metrics"
    __table_args__ = (
        Index(
            "ix_discovered_whale_metrics_run_wallet",
            "run_id",
            "proxy_wallet",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_discovery_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    collection_quality: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[WhaleDiscoveryRun] = relationship(back_populates="metrics")
