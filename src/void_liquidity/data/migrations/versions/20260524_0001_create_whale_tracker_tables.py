from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260524_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whale_tracker_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("profile_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidate_wallet_count", sa.Integer(), nullable=False),
        sa.Column("checked_wallet_count", sa.Integer(), nullable=False),
        sa.Column("accepted_wallet_count", sa.Integer(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("report_path", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "tracked_whales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("proxy_wallet", sa.String(), nullable=False),
        sa.Column("user_name", sa.String(), nullable=True),
        sa.Column("x_username", sa.String(), nullable=True),
        sa.Column("verified_badge", sa.Boolean(), nullable=False),
        sa.Column("candidate_pool_source", sa.String(), nullable=False),
        sa.Column("current_position_value", sa.Float(), nullable=False),
        sa.Column("closed_positions_pnl", sa.Float(), nullable=False),
        sa.Column("roi", sa.Float(), nullable=True),
        sa.Column("profit_factor", sa.Float(), nullable=True),
        sa.Column("activity_volume_window", sa.Float(), nullable=False),
        sa.Column("last_activity_at", sa.String(), nullable=True),
        sa.Column("leaderboard", sa.JSON(), nullable=False),
        sa.Column("exposure", sa.JSON(), nullable=False),
        sa.Column("closed_positions", sa.JSON(), nullable=False),
        sa.Column("activity", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["whale_tracker_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "proxy_wallet",
            name="uq_tracked_whales_run_wallet",
        ),
    )
    op.create_index(
        "ix_tracked_whales_proxy_wallet",
        "tracked_whales",
        ["proxy_wallet"],
        unique=False,
    )
    op.create_index(
        "ix_tracked_whales_run_source",
        "tracked_whales",
        ["run_id", "candidate_pool_source"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tracked_whales_run_source", table_name="tracked_whales")
    op.drop_index("ix_tracked_whales_proxy_wallet", table_name="tracked_whales")
    op.drop_table("tracked_whales")
    op.drop_table("whale_tracker_runs")
