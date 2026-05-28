from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from void_liquidity.data import Base


class WhaleMarketCandidate(Base):
    __tablename__ = "polymarket_whale_market_candidates"
    __table_args__ = (
        Index("ix_whale_market_candidates_condition_id", "condition_id"),
        Index("ix_whale_market_candidates_last_seen_at", "last_seen_at"),
        Index("ix_whale_market_candidates_end_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    condition_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    whale_count: Mapped[int] = mapped_column(Integer, nullable=False)
    wallets: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    total_size: Mapped[float] = mapped_column(Float, nullable=False)
    total_current_value: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    cur_price: Mapped[float] = mapped_column(Float, nullable=False)
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
