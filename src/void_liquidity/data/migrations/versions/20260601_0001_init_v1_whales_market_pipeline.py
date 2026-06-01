"""init v1 whales market pipeline

Revision ID: 20260601_0001
Revises:
Create Date: 2026-06-01 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260601_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_discovery_tables()
    _create_selection_tables()
    _create_candidate_tables()
    _create_qualified_tables()


def downgrade() -> None:
    op.drop_table("polymarket_qualified_market_metric_snapshots")
    op.drop_index(
        "ix_qualified_market_identities_end_date",
        table_name="polymarket_qualified_market_identities",
    )
    op.drop_index(
        "ix_qualified_market_identities_condition_id",
        table_name="polymarket_qualified_market_identities",
    )
    op.drop_index(
        "ux_qualified_market_identities_token_id",
        table_name="polymarket_qualified_market_identities",
    )
    op.drop_table("polymarket_qualified_market_identities")
    op.drop_table("polymarket_qualified_market_runs")

    op.drop_table("polymarket_whale_market_metric_snapshots")
    op.drop_index(
        "ix_whale_market_identities_end_date",
        table_name="polymarket_whale_market_identities",
    )
    op.drop_index(
        "ix_whale_market_identities_condition_id",
        table_name="polymarket_whale_market_identities",
    )
    op.drop_index(
        "ux_whale_market_identities_token_id",
        table_name="polymarket_whale_market_identities",
    )
    op.drop_table("polymarket_whale_market_identities")
    op.drop_table("polymarket_whale_market_candidate_runs")

    op.drop_table("polymarket_selected_whale_metrics")
    op.drop_index(
        "ux_selected_whale_identities_proxy_wallet",
        table_name="polymarket_selected_whale_identities",
    )
    op.drop_table("polymarket_selected_whale_identities")
    op.drop_table("polymarket_whale_selection_runs")

    op.drop_table("polymarket_discovered_whale_metrics")
    op.drop_index(
        "ux_discovered_whale_identities_proxy_wallet",
        table_name="polymarket_discovered_whale_identities",
    )
    op.drop_table("polymarket_discovered_whale_identities")
    op.drop_table("polymarket_whale_discovery_runs")


def _run_columns(*, parent_column: sa.Column | None = None) -> list[sa.Column]:
    columns = [
        sa.Column("run_id", sa.String(), nullable=False),
    ]
    if parent_column is not None:
        columns.append(parent_column)
    columns.extend(
        [
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("config_key", sa.String(), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("error_type", sa.String(), nullable=True),
            sa.Column("error", sa.String(), nullable=True),
        ]
    )
    return columns


def _create_discovery_tables() -> None:
    op.create_table(
        "polymarket_whale_discovery_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("profile_version", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidate_wallet_count", sa.Integer(), nullable=False),
        sa.Column("checked_wallet_count", sa.Integer(), nullable=False),
        sa.Column("accepted_wallet_count", sa.Integer(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "polymarket_discovered_whale_identities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proxy_wallet", sa.String(), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_discovered_whale_identities_proxy_wallet",
        "polymarket_discovered_whale_identities",
        ["proxy_wallet"],
        unique=True,
    )
    op.create_table(
        "polymarket_discovered_whale_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("collection_quality", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_whale_discovery_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["polymarket_discovered_whale_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_discovered_whale_metrics_run_wallet",
        "polymarket_discovered_whale_metrics",
        ["run_id", "identity_id"],
        unique=True,
    )


def _create_selection_tables() -> None:
    op.create_table(
        "polymarket_whale_selection_runs",
        *_run_columns(
            parent_column=sa.Column("discovery_run_id", sa.String(), nullable=False)
        ),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("ranking_method", sa.String(), nullable=False),
        sa.Column("selected_wallet_count", sa.Integer(), nullable=False),
        sa.Column("removed_wallet_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"],
            ["polymarket_whale_discovery_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "polymarket_selected_whale_identities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proxy_wallet", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_selected_whale_identities_proxy_wallet",
        "polymarket_selected_whale_identities",
        ["proxy_wallet"],
        unique=True,
    )
    op.create_table(
        "polymarket_selected_whale_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_whale_selection_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["polymarket_selected_whale_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_selected_whale_metrics_run_wallet",
        "polymarket_selected_whale_metrics",
        ["run_id", "identity_id"],
        unique=True,
    )


def _create_candidate_tables() -> None:
    op.create_table(
        "polymarket_whale_market_candidate_runs",
        *_run_columns(
            parent_column=sa.Column("selection_run_id", sa.String(), nullable=False)
        ),
        sa.Column("min_whale_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["selection_run_id"],
            ["polymarket_whale_selection_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    _create_market_identity_table("polymarket_whale_market_identities", "whale_market")
    op.create_table(
        "polymarket_whale_market_metric_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column("whale_count", sa.Integer(), nullable=False),
        sa.Column("wallets", sa.JSON(), nullable=False),
        sa.Column("total_size", sa.Float(), nullable=False),
        sa.Column("total_current_value", sa.Float(), nullable=False),
        sa.Column("weighted_avg_price", sa.Float(), nullable=False),
        sa.Column("cur_price", sa.Float(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_whale_market_candidate_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["polymarket_whale_market_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_whale_market_metric_snapshots_run_token",
        "polymarket_whale_market_metric_snapshots",
        ["run_id", "identity_id"],
        unique=True,
    )
    op.create_index(
        "ix_whale_market_metric_snapshots_identity_id",
        "polymarket_whale_market_metric_snapshots",
        ["identity_id"],
        unique=False,
    )


def _create_qualified_tables() -> None:
    op.create_table(
        "polymarket_qualified_market_runs",
        *_run_columns(
            parent_column=sa.Column("candidate_run_id", sa.String(), nullable=False)
        ),
        sa.Column("profiles", sa.JSON(), nullable=False),
        sa.Column("qualified_market_count", sa.Integer(), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_run_id"],
            ["polymarket_whale_market_candidate_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    _create_market_identity_table(
        "polymarket_qualified_market_identities",
        "qualified_market",
    )
    op.create_table(
        "polymarket_qualified_market_metric_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column("profile_name", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("price_delta", sa.Float(), nullable=False),
        sa.Column("price_delta_pct", sa.Float(), nullable=True),
        sa.Column("value_per_wallet", sa.Float(), nullable=False),
        sa.Column("candidate", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["polymarket_qualified_market_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["polymarket_qualified_market_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_qualified_market_metric_snapshots_run_token_profile",
        "polymarket_qualified_market_metric_snapshots",
        ["run_id", "identity_id", "profile_name"],
        unique=True,
    )
    op.create_index(
        "ix_qualified_market_metric_snapshots_identity_id",
        "polymarket_qualified_market_metric_snapshots",
        ["identity_id"],
        unique=False,
    )


def _create_market_identity_table(table_name: str, index_prefix: str) -> None:
    op.create_table(
        table_name,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("opposite_token_id", sa.String(), nullable=True),
        sa.Column("opposite_outcome", sa.String(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("negative_risk", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        f"ux_{index_prefix}_identities_token_id",
        table_name,
        ["token_id"],
        unique=True,
    )
    op.create_index(
        f"ix_{index_prefix}_identities_condition_id",
        table_name,
        ["condition_id"],
        unique=False,
    )
    op.create_index(
        f"ix_{index_prefix}_identities_end_date",
        table_name,
        ["end_date"],
        unique=False,
    )
