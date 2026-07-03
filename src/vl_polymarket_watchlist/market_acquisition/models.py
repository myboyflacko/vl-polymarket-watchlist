from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vl_polymarket_watchlist.core.db.base import Base


class Market(Base):
    __tablename__ = "polymarket_markets"
    __table_args__ = (
        Index("ux_polymarket_markets_token_id", "token_id", unique=True),
        Index("ix_polymarket_markets_condition_id", "condition_id"),
        Index("ix_polymarket_markets_end_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String, nullable=False)
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    slug: Mapped[str] = mapped_column(String, nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String, nullable=False, default="")
    opposite_token_id: Mapped[str | None] = mapped_column(String, nullable=True)
    opposite_outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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


class CollectorRun(Base):
    __tablename__ = "polymarket_collector_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String, nullable=False)
    strategy_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_market_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stored_market_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    markets: Mapped[list["CollectorRunMarket"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class CollectorRunMarket(Base):
    __tablename__ = "polymarket_collector_run_markets"
    __table_args__ = (
        Index(
            "ux_polymarket_collector_run_markets_run_market",
            "run_id",
            "market_id",
            unique=True,
        ),
        Index("ix_polymarket_collector_run_markets_market_id", "market_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("polymarket_collector_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    market_id: Mapped[int] = mapped_column(
        ForeignKey("polymarket_markets.id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[CollectorRun] = relationship(back_populates="markets")
    market: Mapped[Market] = relationship(lazy="joined")
