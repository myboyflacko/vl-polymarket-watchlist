"""remove tracker legacy metrics

Revision ID: c41d9a67e2f4
Revises: 8a4ef1b3b1d1
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c41d9a67e2f4"
down_revision: Union[str, Sequence[str], None] = "8a4ef1b3b1d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ux_polymarket_market_metrics_run_market",
        table_name="polymarket_market_metrics",
    )
    op.drop_index(
        "ix_polymarket_market_metrics_market_id",
        table_name="polymarket_market_metrics",
    )
    op.drop_table("polymarket_market_metrics")

    op.drop_index(
        "ux_polymarket_whale_metrics_run_whale",
        table_name="polymarket_whale_metrics",
    )
    op.drop_index(
        "ix_polymarket_whale_metrics_whale_id",
        table_name="polymarket_whale_metrics",
    )
    op.drop_table("polymarket_whale_metrics")

    op.add_column(
        "polymarket_whale_runs",
        sa.Column("observed_wallet_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_whale_runs",
        sa.Column("tracked_wallet_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_column("polymarket_whale_runs", "filter_profile")
    op.drop_column("polymarket_whale_runs", "scoring_profile")
    op.drop_column("polymarket_whale_runs", "filtered_wallet_count")
    op.drop_column("polymarket_whale_runs", "scored_wallet_count")
    op.drop_column("polymarket_whale_runs", "removed_wallet_count")

    op.create_table(
        "polymarket_whale_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("whale_id", sa.Integer(), nullable=False),
        sa.Column("candidate_source", sa.String(), nullable=False),
        sa.Column("pnl_rank", sa.Integer(), nullable=True),
        sa.Column("volume_rank", sa.Integer(), nullable=True),
        sa.Column("leaderboard_pnl", sa.Float(), nullable=False),
        sa.Column("leaderboard_volume", sa.Float(), nullable=False),
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
        "ix_polymarket_whale_observations_whale_id",
        "polymarket_whale_observations",
        ["whale_id"],
        unique=False,
    )
    op.create_index(
        "ux_polymarket_whale_observations_run_whale",
        "polymarket_whale_observations",
        ["run_id", "whale_id"],
        unique=True,
    )

    op.execute("DELETE FROM polymarket_tracked_whales")
    op.add_column(
        "polymarket_tracked_whales",
        sa.Column("candidate_source", sa.String(), nullable=False, server_default="pnl"),
    )
    op.add_column(
        "polymarket_tracked_whales",
        sa.Column("pnl_rank", sa.Integer(), nullable=True),
    )
    op.add_column(
        "polymarket_tracked_whales",
        sa.Column("volume_rank", sa.Integer(), nullable=True),
    )
    op.add_column(
        "polymarket_tracked_whales",
        sa.Column("leaderboard_pnl", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_tracked_whales",
        sa.Column("leaderboard_volume", sa.Float(), nullable=False, server_default="0"),
    )
    op.drop_column("polymarket_tracked_whales", "metrics")

    op.add_column(
        "polymarket_market_runs",
        sa.Column("tracked_market_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_column("polymarket_market_runs", "filter_profile")
    op.drop_column("polymarket_market_runs", "scoring_profile")
    op.drop_column("polymarket_market_runs", "filtered_market_count")
    op.drop_column("polymarket_market_runs", "scored_market_count")
    op.drop_column("polymarket_market_runs", "removed_market_count")
    op.drop_column("polymarket_market_runs", "limit")

    op.execute("DELETE FROM polymarket_tracked_markets")
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("whale_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("wallets", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("total_size", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("total_current_value", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("weighted_avg_price", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("cur_price", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("negative_risk", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.drop_column("polymarket_tracked_markets", "metrics")


def downgrade() -> None:
    op.add_column(
        "polymarket_tracked_markets",
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.drop_column("polymarket_tracked_markets", "negative_risk")
    op.drop_column("polymarket_tracked_markets", "cur_price")
    op.drop_column("polymarket_tracked_markets", "weighted_avg_price")
    op.drop_column("polymarket_tracked_markets", "total_current_value")
    op.drop_column("polymarket_tracked_markets", "total_size")
    op.drop_column("polymarket_tracked_markets", "wallets")
    op.drop_column("polymarket_tracked_markets", "whale_count")

    op.add_column("polymarket_market_runs", sa.Column("limit", sa.Integer(), nullable=True))
    op.add_column(
        "polymarket_market_runs",
        sa.Column("removed_market_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_market_runs",
        sa.Column("scored_market_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_market_runs",
        sa.Column("filtered_market_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_market_runs",
        sa.Column("scoring_profile", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "polymarket_market_runs",
        sa.Column("filter_profile", sa.String(), nullable=False, server_default=""),
    )
    op.drop_column("polymarket_market_runs", "tracked_market_count")

    op.add_column(
        "polymarket_tracked_whales",
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.drop_column("polymarket_tracked_whales", "leaderboard_volume")
    op.drop_column("polymarket_tracked_whales", "leaderboard_pnl")
    op.drop_column("polymarket_tracked_whales", "volume_rank")
    op.drop_column("polymarket_tracked_whales", "pnl_rank")
    op.drop_column("polymarket_tracked_whales", "candidate_source")

    op.drop_index(
        "ux_polymarket_whale_observations_run_whale",
        table_name="polymarket_whale_observations",
    )
    op.drop_index(
        "ix_polymarket_whale_observations_whale_id",
        table_name="polymarket_whale_observations",
    )
    op.drop_table("polymarket_whale_observations")

    op.add_column(
        "polymarket_whale_runs",
        sa.Column("removed_wallet_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_whale_runs",
        sa.Column("scored_wallet_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_whale_runs",
        sa.Column("filtered_wallet_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "polymarket_whale_runs",
        sa.Column("scoring_profile", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "polymarket_whale_runs",
        sa.Column("filter_profile", sa.String(), nullable=False, server_default=""),
    )
    op.drop_column("polymarket_whale_runs", "tracked_wallet_count")
    op.drop_column("polymarket_whale_runs", "observed_wallet_count")

    op.create_table(
        "polymarket_whale_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("whale_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
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
        "ix_polymarket_whale_metrics_whale_id",
        "polymarket_whale_metrics",
        ["whale_id"],
        unique=False,
    )
    op.create_index(
        "ux_polymarket_whale_metrics_run_whale",
        "polymarket_whale_metrics",
        ["run_id", "whale_id"],
        unique=True,
    )

    op.create_table(
        "polymarket_market_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
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
        "ix_polymarket_market_metrics_market_id",
        "polymarket_market_metrics",
        ["market_id"],
        unique=False,
    )
    op.create_index(
        "ux_polymarket_market_metrics_run_market",
        "polymarket_market_metrics",
        ["run_id", "market_id"],
        unique=True,
    )
