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
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ranking_method: Mapped[str] = mapped_column(String, nullable=False)
    selected_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False)
    removed_wallet_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[list["SelectedWhaleMetric"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="SelectedWhaleMetric.rank",
    )


class SelectedWhale(Base):
    __tablename__ = "polymarket_selected_whales"
    __table_args__ = (
        Index(
            "ux_selected_whales_proxy_wallet",
            "proxy_wallet",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SelectedWhaleMetric(Base):
    __tablename__ = "polymarket_selected_whale_metrics"
    __table_args__ = (
        Index(
            "ux_selected_whale_metrics_run_wallet",
            "run_id",
            "proxy_wallet",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_selection_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    proxy_wallet: Mapped[str] = mapped_column(String, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[WhaleSelectionRun] = relationship(back_populates="metrics")
