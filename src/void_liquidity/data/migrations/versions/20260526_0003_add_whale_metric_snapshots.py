"""add whale metric snapshots

Revision ID: 20260526_0003
Revises: 20260525_0002
Create Date: 2026-05-26 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260526_0003"
down_revision: str | Sequence[str] | None = "20260525_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracked_whale_metric_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("proxy_wallet", sa.String(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("collection_quality", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["whale_tracker_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tracked_whale_metric_snapshots_run_wallet",
        "tracked_whale_metric_snapshots",
        ["run_id", "proxy_wallet"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tracked_whale_metric_snapshots_run_wallet",
        table_name="tracked_whale_metric_snapshots",
    )
    op.drop_table("tracked_whale_metric_snapshots")
