"""init

Revision ID: b0b6ccc576db
Revises:
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b0b6ccc576db"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
        "ix_polymarket_markets_condition_id",
        "polymarket_markets",
        ["condition_id"],
        unique=False,
    )
    op.create_index(
        "ix_polymarket_markets_end_date",
        "polymarket_markets",
        ["end_date"],
        unique=False,
    )
    op.create_index(
        "ux_polymarket_markets_token_id",
        "polymarket_markets",
        ["token_id"],
        unique=True,
    )

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
        sa.Column("tracked_wallet_count", sa.Integer(), nullable=False),
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
        "polymarket_market_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("whales_run_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_market_count", sa.Integer(), nullable=False),
        sa.Column("tracked_market_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["whales_run_id"],
            ["polymarket_whale_runs.run_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )

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

    op.create_table(
        "polymarket_tracked_whales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("whale_id", sa.Integer(), nullable=False),
        sa.Column("filter_profile", sa.String(), nullable=False),
        sa.Column("consecutive_runs", sa.Integer(), nullable=False),
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
        sa.Column("whale_count", sa.Integer(), nullable=False),
        sa.Column("wallets", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("total_size", sa.Float(), nullable=False),
        sa.Column("total_current_value", sa.Float(), nullable=False),
        sa.Column("weighted_avg_price", sa.Float(), nullable=False),
        sa.Column("cur_price", sa.Float(), nullable=False),
        sa.Column("negative_risk", sa.Boolean(), nullable=False),
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

    op.drop_index(
        "ux_polymarket_whale_observations_run_whale",
        table_name="polymarket_whale_observations",
    )
    op.drop_index(
        "ix_polymarket_whale_observations_whale_id",
        table_name="polymarket_whale_observations",
    )
    op.drop_table("polymarket_whale_observations")

    op.drop_table("polymarket_market_runs")

    op.drop_index(
        "ux_polymarket_whales_proxy_wallet",
        table_name="polymarket_whales",
    )
    op.drop_table("polymarket_whales")

    op.drop_table("polymarket_whale_runs")

    op.drop_index(
        "ux_polymarket_markets_token_id",
        table_name="polymarket_markets",
    )
    op.drop_index(
        "ix_polymarket_markets_end_date",
        table_name="polymarket_markets",
    )
    op.drop_index(
        "ix_polymarket_markets_condition_id",
        table_name="polymarket_markets",
    )
    op.drop_table("polymarket_markets")
