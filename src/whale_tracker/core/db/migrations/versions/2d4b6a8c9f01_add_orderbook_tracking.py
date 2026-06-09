"""add orderbook tracking

Revision ID: 2d4b6a8c9f01
Revises: b0b6ccc576db
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d4b6a8c9f01"
down_revision: Union[str, Sequence[str], None] = "b0b6ccc576db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("tracked_market_id", sa.Integer(), nullable=False),
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
            ["tracked_market_id"],
            ["polymarket_tracked_markets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_polymarket_orderbook_metrics_generated_at",
        "polymarket_orderbook_metrics",
        ["generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_polymarket_orderbook_metrics_run_id",
        "polymarket_orderbook_metrics",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_polymarket_orderbook_metrics_tracked_market_id",
        "polymarket_orderbook_metrics",
        ["tracked_market_id"],
        unique=False,
    )
    op.create_index(
        "ux_polymarket_orderbook_metrics_run_tracked_market",
        "polymarket_orderbook_metrics",
        ["run_id", "tracked_market_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_polymarket_orderbook_metrics_run_tracked_market",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_index(
        "ix_polymarket_orderbook_metrics_tracked_market_id",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_index(
        "ix_polymarket_orderbook_metrics_run_id",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_index(
        "ix_polymarket_orderbook_metrics_generated_at",
        table_name="polymarket_orderbook_metrics",
    )
    op.drop_table("polymarket_orderbook_metrics")
    op.drop_table("polymarket_orderbook_runs")
