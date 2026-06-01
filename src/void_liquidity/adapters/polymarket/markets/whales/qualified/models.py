from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String
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
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    qualified_market_count: Mapped[int] = mapped_column(Integer, nullable=False)
    limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    markets: Mapped[list["QualifiedMarketRow"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="QualifiedMarketRow.rank",
    )


class QualifiedMarketRow(Base):
    __tablename__ = "polymarket_qualified_markets"
    __table_args__ = (
        Index(
            "ux_qualified_markets_run_token_profile",
            "run_id",
            "token_id",
            "profile_name",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_qualified_market_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_id: Mapped[str] = mapped_column(String, nullable=False)
    profile_name: Mapped[str] = mapped_column(String, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    price_delta: Mapped[float] = mapped_column(Float, nullable=False)
    price_delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_per_wallet: Mapped[float] = mapped_column(Float, nullable=False)
    candidate: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[QualifiedMarketRun] = relationship(back_populates="markets")
