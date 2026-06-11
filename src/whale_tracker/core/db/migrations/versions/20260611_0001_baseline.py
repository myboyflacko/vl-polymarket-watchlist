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
        "polymarket_whale_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("profile_version", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_wallet_count", sa.Integer(), nullable=False),
        sa.Column("observed_wallet_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "polymarket_whales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proxy_wallet", sa.String(), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
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
        "ux_polymarket_whales_proxy_wallet",
        "polymarket_whales",
        ["proxy_wallet"],
        unique=True,
    )
    op.create_table(
        "polymarket_whale_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("whale_id", sa.Integer(), nullable=False),
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
        "ux_polymarket_whale_observations_run_whale",
        "polymarket_whale_observations",
        ["run_id", "whale_id"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_whale_observations_whale_id",
        "polymarket_whale_observations",
        ["whale_id"],
    )

    op.create_table(
        "polymarket_market_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("whales_run_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_market_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["whales_run_id"],
            ["polymarket_whale_runs.run_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
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
        "polymarket_market_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("wallet", sa.String(), nullable=False),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("cur_price", sa.Float(), nullable=False),
        sa.Column("negative_risk", sa.Boolean(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["polymarket_markets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_market_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
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

    op.create_table(
        "polymarket_orderbook_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("market_run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("checked_market_count", sa.Integer(), nullable=False),
        sa.Column("stored_orderbook_count", sa.Integer(), nullable=False),
        sa.Column("failed_orderbook_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["market_run_id"],
            ["polymarket_market_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "polymarket_orderbook_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("exchange_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exchange_timestamp_raw", sa.String(), nullable=True),
        sa.Column("book_hash", sa.String(), nullable=False),
        sa.Column("bids", sa.JSON(), nullable=False),
        sa.Column("asks", sa.JSON(), nullable=False),
        sa.Column("best_bid", sa.Float(), nullable=True),
        sa.Column("best_ask", sa.Float(), nullable=True),
        sa.Column("spread", sa.Float(), nullable=True),
        sa.Column("midpoint", sa.Float(), nullable=True),
        sa.Column("min_order_size", sa.Float(), nullable=True),
        sa.Column("tick_size", sa.Float(), nullable=True),
        sa.Column("negative_risk", sa.Boolean(), nullable=False),
        sa.Column("last_trade_price", sa.Float(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_orderbook_runs.run_id"],
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
        "ux_polymarket_orderbook_metrics_run_market",
        "polymarket_orderbook_metrics",
        ["run_id", "market_id"],
        unique=True,
    )
    op.create_index(
        "ix_polymarket_orderbook_metrics_run_id",
        "polymarket_orderbook_metrics",
        ["run_id"],
    )
    op.create_index(
        "ix_polymarket_orderbook_metrics_market_id",
        "polymarket_orderbook_metrics",
        ["market_id"],
    )
    op.create_index(
        "ix_polymarket_orderbook_metrics_generated_at",
        "polymarket_orderbook_metrics",
        ["generated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_polymarket_orderbook_metrics_generated_at",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_index(
        "ix_polymarket_orderbook_metrics_market_id",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_index(
        "ix_polymarket_orderbook_metrics_run_id",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_index(
        "ux_polymarket_orderbook_metrics_run_market",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_table("polymarket_orderbook_metrics")
    op.drop_table("polymarket_orderbook_runs")

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
    op.drop_table("polymarket_market_observations")
    op.drop_index("ix_polymarket_markets_end_date", table_name="polymarket_markets")
    op.drop_index(
        "ix_polymarket_markets_condition_id",
        table_name="polymarket_markets",
    )
    op.drop_index("ux_polymarket_markets_token_id", table_name="polymarket_markets")
    op.drop_table("polymarket_markets")
    op.drop_table("polymarket_market_runs")

    op.drop_index(
        "ix_polymarket_whale_observations_whale_id",
        table_name="polymarket_whale_observations",
    )
    op.drop_index(
        "ux_polymarket_whale_observations_run_whale",
        table_name="polymarket_whale_observations",
    )
    op.drop_table("polymarket_whale_observations")
    op.drop_index("ux_polymarket_whales_proxy_wallet", table_name="polymarket_whales")
    op.drop_table("polymarket_whales")
    op.drop_table("polymarket_whale_runs")
