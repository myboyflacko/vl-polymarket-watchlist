from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from void_liquidity.data.base import Base
from void_liquidity.adapters.polymarket.markets.whales.candidates import (
    models as _candidate_models,
)


_ = _candidate_models


class QualifiedMarketRun(Base):
    __tablename__ = "polymarket_qualified_market_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_market_candidate_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    config_key: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profiles: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    qualified_market_count: Mapped[int] = mapped_column(Integer, nullable=False)
    limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshots: Mapped[list["QualifiedMarketMetricSnapshot"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="QualifiedMarketMetricSnapshot.rank",
    )


class QualifiedMarketIdentity(Base):
    __tablename__ = "polymarket_qualified_market_identities"
    __table_args__ = (
        Index("ux_qualified_market_identities_token_id", "token_id", unique=True),
        Index("ix_qualified_market_identities_condition_id", "condition_id"),
        Index("ix_qualified_market_identities_end_date", "end_date"),
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
    negative_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshots: Mapped[list["QualifiedMarketMetricSnapshot"]] = relationship(
        back_populates="market",
        cascade="all, delete-orphan",
        order_by="QualifiedMarketMetricSnapshot.id",
    )


class QualifiedMarketMetricSnapshot(Base):
    __tablename__ = "polymarket_qualified_market_metric_snapshots"
    __table_args__ = (
        Index(
            "ux_qualified_market_metric_snapshots_run_token_profile",
            "run_id",
            "identity_id",
            "profile_name",
            unique=True,
        ),
        Index("ix_qualified_market_metric_snapshots_identity_id", "identity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_qualified_market_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_qualified_market_identities.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_name: Mapped[str] = mapped_column(String, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    price_delta: Mapped[float] = mapped_column(Float, nullable=False)
    price_delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_per_wallet: Mapped[float] = mapped_column(Float, nullable=False)
    candidate: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[QualifiedMarketRun] = relationship(back_populates="snapshots")
    market: Mapped[QualifiedMarketIdentity] = relationship(
        back_populates="snapshots",
        lazy="joined",
    )

    @property
    def token_id(self) -> str:
        return self.market.token_id
