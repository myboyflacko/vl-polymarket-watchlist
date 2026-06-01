from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from void_liquidity.data.base import Base
from void_liquidity.adapters.polymarket.markets.whales.discovery import (
    models as _discovery_models,
)


_ = _discovery_models


class WhaleSelectionRun(Base):
    __tablename__ = "polymarket_whale_selection_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    discovery_run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_discovery_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    config_key: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ranking_method: Mapped[str] = mapped_column(String, nullable=False)
    selected_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    metrics: Mapped[list["SelectedWhaleMetric"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="SelectedWhaleMetric.rank",
    )


class SelectedWhale(Base):
    __tablename__ = "polymarket_whale_selection_identities"
    __table_args__ = (
        Index(
            "ux_whale_selection_identities_proxy_wallet",
            "proxy_wallet",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[list["SelectedWhaleMetric"]] = relationship(
        back_populates="identity",
        cascade="all, delete-orphan",
        order_by="SelectedWhaleMetric.id",
    )


class SelectedWhaleMetric(Base):
    __tablename__ = "polymarket_whale_selection_metric_snapshots"
    __table_args__ = (
        Index(
            "ux_whale_selection_metric_snapshots_run_identity",
            "run_id",
            "identity_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_selection_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_whale_selection_identities.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[WhaleSelectionRun] = relationship(back_populates="metrics")
    identity: Mapped[SelectedWhale] = relationship(
        back_populates="metrics",
        lazy="joined",
    )

    @property
    def proxy_wallet(self) -> str:
        return self.identity.proxy_wallet
