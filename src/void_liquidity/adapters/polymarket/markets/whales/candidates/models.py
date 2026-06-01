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
    __tablename__ = "polymarket_whale_candidate_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    selection_run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_selection_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    config_key: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    min_whale_count: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshots: Mapped[list["WhaleMarketMetricSnapshot"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="WhaleMarketMetricSnapshot.id",
    )


class WhaleMarket(Base):
    __tablename__ = "polymarket_whale_candidate_identities"
    __table_args__ = (
        Index("ux_whale_candidate_identities_token_id", "token_id", unique=True),
        Index("ix_whale_candidate_identities_condition_id", "condition_id"),
        Index("ix_whale_candidate_identities_end_date", "end_date"),
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
    __tablename__ = "polymarket_whale_candidate_metric_snapshots"
    __table_args__ = (
        Index(
            "ux_whale_candidate_metric_snapshots_run_identity",
            "run_id",
            "identity_id",
            unique=True,
        ),
        Index("ix_whale_candidate_metric_snapshots_identity_id", "identity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_whale_candidate_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    identity_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_whale_candidate_identities.id", ondelete="CASCADE"),
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
    market: Mapped[WhaleMarket] = relationship(back_populates="snapshots", lazy="joined")

    @property
    def token_id(self) -> str:
        return self.market.token_id
