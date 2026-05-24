from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from void_liquidity.adapters.polymarket.market_discovery.sources.track_whales.config import (
    _resolve_project_path,
)
from void_liquidity.adapters.polymarket.market_discovery.sources.track_whales.metrics import (
    _build_payload,
)
from void_liquidity.adapters.polymarket.market_discovery.sources.track_whales.schemas import (
    WhaleTrackingProfile,
)


class Base(DeclarativeBase):
    pass


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


def build_sqlite_url(database_path: str | Path) -> str:
    resolved_path = _resolve_project_path(database_path)
    return f"sqlite:///{resolved_path}"


def create_whale_tracker_engine(database_path: str | Path) -> Engine:
    resolved_path = _resolve_project_path(database_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{resolved_path}", future=True)


@contextmanager
def whale_tracker_session(database_path: str | Path) -> Iterator[Session]:
    engine = create_whale_tracker_engine(database_path)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        yield session


def persist_whale_tracker_run(
    *,
    profile: WhaleTrackingProfile,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    generated_at: datetime,
    candidate_wallet_count: int,
    checked_wallet_count: int,
    whales: dict[str, dict[str, Any]],
    report_path: Path,
) -> None:
    public_whales = _build_payload(whales=whales, run_id=run_id)["whales"]

    with whale_tracker_session(profile.database_path) as session:
        session.add(
            WhaleTrackerRun(
                run_id=run_id,
                profile_version=profile.profile_version,
                status="completed",
                started_at=started_at,
                finished_at=finished_at,
                generated_at=generated_at,
                candidate_wallet_count=candidate_wallet_count,
                checked_wallet_count=checked_wallet_count,
                accepted_wallet_count=len(public_whales),
                profile=profile.model_dump(mode="json"),
                report_path=str(report_path),
            )
        )
        session.add_all(
            _tracked_whale_row(run_id=run_id, whale=whale)
            for whale in public_whales.values()
        )
        session.commit()


def _tracked_whale_row(run_id: str, whale: dict[str, Any]) -> TrackedWhale:
    metadata = whale["metadata"]
    metrics = whale["metrics"]
    leaderboard = metrics["leaderboard"]
    exposure = metrics["exposure"]
    closed_positions = metrics["closed_positions"]
    activity = metrics["activity"]

    return TrackedWhale(
        run_id=run_id,
        proxy_wallet=metadata["proxy_wallet"],
        user_name=metadata["user_name"],
        x_username=metadata["x_username"],
        verified_badge=metadata["verified_badge"],
        candidate_pool_source=leaderboard["candidate_pool_source"],
        current_position_value=exposure["current_position_value"],
        closed_positions_pnl=closed_positions["closed_positions_pnl"],
        roi=closed_positions["roi"],
        profit_factor=closed_positions["profit_factor"],
        activity_volume_window=activity["activity_volume_window"],
        last_activity_at=activity["last_activity_at"],
        leaderboard=leaderboard,
        exposure=exposure,
        closed_positions=closed_positions,
        activity=activity,
    )
