"""Rename market observations and add trade tracking.

Revision ID: 20260611_0002
Revises: 20260611_0001
Create Date: 2026-06-11 00:02:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260611_0002"
down_revision: str | None = "20260611_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "ix_polymarket_market_observations_market_id",
        table_name="polymarket_market_observations",
    )
    op.drop_index(
        "ix_polymarket_market_observations_run_id",
        table_name="polymarket_market_observations",
    )
    op.drop_index(
        "ux_polymarket_market_observations_run_wallet_market",
        table_name="polymarket_market_observations",
    )
    op.rename_table("polymarket_market_observations", "polymarket_market_positions")
    op.create_index(
        "ux_polymarket_market_positions_run_wallet_market",
        "polymarket_market_positions",
        ["run_id", "wallet", "market_id"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_market_positions_run_id",
        "polymarket_market_positions",
        ["run_id"],
    )
    op.create_index(
        "ix_polymarket_market_positions_market_id",
        "polymarket_market_positions",
        ["market_id"],
    )

    op.create_table(
        "polymarket_trade_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("market_run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_source_count", sa.Integer(), nullable=False),
        sa.Column("stored_trade_count", sa.Integer(), nullable=False),
        sa.Column("failed_source_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["market_run_id"],
            ["polymarket_market_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "polymarket_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_key", sa.String(), nullable=False),
        sa.Column("wallet", sa.String(), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.String(), nullable=True),
        sa.Column("side", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("size", sa.Float(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("trade_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transaction_hash", sa.String(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["polymarket_markets.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_polymarket_trades_trade_key",
        "polymarket_trades",
        ["trade_key"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_trades_wallet_condition",
        "polymarket_trades",
        ["wallet", "condition_id"],
    )
    op.create_index(
        "ix_polymarket_trades_market_id",
        "polymarket_trades",
        ["market_id"],
    )
    op.create_index(
        "ix_polymarket_trades_trade_timestamp",
        "polymarket_trades",
        ["trade_timestamp"],
    )
    op.create_table(
        "polymarket_trade_run_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_trade_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["polymarket_trades.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_polymarket_trade_run_items_run_trade",
        "polymarket_trade_run_items",
        ["run_id", "trade_id"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_trade_run_items_trade_id",
        "polymarket_trade_run_items",
        ["trade_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_polymarket_trade_run_items_trade_id",
        table_name="polymarket_trade_run_items",
    )
    op.drop_index(
        "ux_polymarket_trade_run_items_run_trade",
        table_name="polymarket_trade_run_items",
    )
    op.drop_table("polymarket_trade_run_items")
    op.drop_index(
        "ix_polymarket_trades_trade_timestamp",
        table_name="polymarket_trades",
    )
    op.drop_index("ix_polymarket_trades_market_id", table_name="polymarket_trades")
    op.drop_index(
        "ix_polymarket_trades_wallet_condition",
        table_name="polymarket_trades",
    )
    op.drop_index("ux_polymarket_trades_trade_key", table_name="polymarket_trades")
    op.drop_table("polymarket_trades")
    op.drop_table("polymarket_trade_runs")

    op.drop_index(
        "ix_polymarket_market_positions_market_id",
        table_name="polymarket_market_positions",
    )
    op.drop_index(
        "ix_polymarket_market_positions_run_id",
        table_name="polymarket_market_positions",
    )
    op.drop_index(
        "ux_polymarket_market_positions_run_wallet_market",
        table_name="polymarket_market_positions",
    )
    op.rename_table("polymarket_market_positions", "polymarket_market_observations")
    op.create_index(
        "ux_polymarket_market_observations_run_wallet_market",
        "polymarket_market_observations",
        ["run_id", "wallet", "market_id"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_market_observations_run_id",
        "polymarket_market_observations",
        ["run_id"],
    )
    op.create_index(
        "ix_polymarket_market_observations_market_id",
        "polymarket_market_observations",
        ["market_id"],
    )
