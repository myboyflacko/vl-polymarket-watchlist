"""link tracked whales to tracker runs

Revision ID: 20260525_0002
Revises: d2356fc50388
Create Date: 2026-05-25 20:10:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260525_0002"
down_revision: str | Sequence[str] | None = "d2356fc50388"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tracked_whales") as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tracked_whales_run_id_whale_tracker_runs",
            "whale_tracker_runs",
            ["run_id"],
            ["run_id"],
            ondelete="CASCADE",
        )

    op.execute(
        sa.text(
            """
            UPDATE tracked_whales
            SET run_id = (
                SELECT run_id
                FROM whale_tracker_runs
                ORDER BY generated_at DESC
                LIMIT 1
            )
            WHERE run_id IS NULL
            """
        )
    )

    with op.batch_alter_table("tracked_whales") as batch_op:
        batch_op.alter_column(
            "run_id",
            existing_type=sa.String(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("tracked_whales") as batch_op:
        batch_op.drop_constraint(
            "fk_tracked_whales_run_id_whale_tracker_runs",
            type_="foreignkey",
        )
        batch_op.drop_column("run_id")
