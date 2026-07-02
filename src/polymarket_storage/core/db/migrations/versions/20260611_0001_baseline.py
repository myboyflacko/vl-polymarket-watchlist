"""Baseline schema.

Revision ID: 20260611_0001
Revises:
Create Date: 2026-06-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260611_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "polymarket_markets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("opposite_token_id", sa.String(), nullable=True),
        sa.Column("opposite_outcome", sa.String(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_polymarket_markets_token_id",
        "polymarket_markets",
        ["token_id"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_markets_condition_id",
        "polymarket_markets",
        ["condition_id"],
    )
    op.create_index(
        "ix_polymarket_markets_end_date",
        "polymarket_markets",
        ["end_date"],
    )

    op.create_table(
        "polymarket_collector_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("strategy_name", sa.String(), nullable=False),
        sa.Column("strategy_params", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_market_count", sa.Integer(), nullable=False),
        sa.Column("stored_market_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "polymarket_collector_run_markets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["polymarket_markets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_collector_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_polymarket_collector_run_markets_run_market",
        "polymarket_collector_run_markets",
        ["run_id", "market_id"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_collector_run_markets_market_id",
        "polymarket_collector_run_markets",
        ["market_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_polymarket_collector_run_markets_market_id",
        table_name="polymarket_collector_run_markets",
    )
    op.drop_index(
        "ux_polymarket_collector_run_markets_run_market",
        table_name="polymarket_collector_run_markets",
    )
    op.drop_table("polymarket_collector_run_markets")
    op.drop_table("polymarket_collector_runs")

    op.drop_index("ix_polymarket_markets_end_date", table_name="polymarket_markets")
    op.drop_index(
        "ix_polymarket_markets_condition_id",
        table_name="polymarket_markets",
    )
    op.drop_index("ux_polymarket_markets_token_id", table_name="polymarket_markets")
    op.drop_table("polymarket_markets")
