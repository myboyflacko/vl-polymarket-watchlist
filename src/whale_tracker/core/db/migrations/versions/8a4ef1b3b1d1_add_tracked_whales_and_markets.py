"""add tracked whales and markets

Revision ID: 8a4ef1b3b1d1
Revises: b0b6ccc576db
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a4ef1b3b1d1"
down_revision: Union[str, Sequence[str], None] = "b0b6ccc576db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "polymarket_tracked_whales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("whale_id", sa.Integer(), nullable=False),
        sa.Column("filter_profile", sa.String(), nullable=False),
        sa.Column("consecutive_runs", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_whale_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["whale_id"],
            ["polymarket_whales.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_polymarket_tracked_whales_run_id",
        "polymarket_tracked_whales",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_polymarket_tracked_whales_whale_id",
        "polymarket_tracked_whales",
        ["whale_id"],
        unique=False,
    )
    op.create_index(
        "ux_polymarket_tracked_whales_run_whale_filter",
        "polymarket_tracked_whales",
        ["run_id", "whale_id", "filter_profile"],
        unique=True,
    )

    op.create_table(
        "polymarket_tracked_markets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("filter_profile", sa.String(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_market_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["polymarket_markets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_polymarket_tracked_markets_market_id",
        "polymarket_tracked_markets",
        ["market_id"],
        unique=False,
    )
    op.create_index(
        "ix_polymarket_tracked_markets_run_id",
        "polymarket_tracked_markets",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ux_polymarket_tracked_markets_run_market_filter",
        "polymarket_tracked_markets",
        ["run_id", "market_id", "filter_profile"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_polymarket_tracked_markets_run_market_filter",
        table_name="polymarket_tracked_markets",
    )
    op.drop_index(
        "ix_polymarket_tracked_markets_run_id",
        table_name="polymarket_tracked_markets",
    )
    op.drop_index(
        "ix_polymarket_tracked_markets_market_id",
        table_name="polymarket_tracked_markets",
    )
    op.drop_table("polymarket_tracked_markets")
    op.drop_index(
        "ux_polymarket_tracked_whales_run_whale_filter",
        table_name="polymarket_tracked_whales",
    )
    op.drop_index(
        "ix_polymarket_tracked_whales_whale_id",
        table_name="polymarket_tracked_whales",
    )
    op.drop_index(
        "ix_polymarket_tracked_whales_run_id",
        table_name="polymarket_tracked_whales",
    )
    op.drop_table("polymarket_tracked_whales")
