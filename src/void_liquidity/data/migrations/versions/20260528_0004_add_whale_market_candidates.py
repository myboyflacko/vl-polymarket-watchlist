"""add whale market candidates

Revision ID: 20260528_0004
Revises: 20260526_0003
Create Date: 2026-05-28 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260528_0004"
down_revision: str | Sequence[str] | None = "20260526_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "polymarket_whale_market_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("whale_count", sa.Integer(), nullable=False),
        sa.Column("wallets", sa.JSON(), nullable=False),
        sa.Column("total_size", sa.Float(), nullable=False),
        sa.Column("total_current_value", sa.Float(), nullable=False),
        sa.Column("weighted_avg_price", sa.Float(), nullable=False),
        sa.Column("cur_price", sa.Float(), nullable=False),
        sa.Column("opposite_token_id", sa.String(), nullable=True),
        sa.Column("opposite_outcome", sa.String(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("negative_risk", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id"),
    )
    op.create_index(
        "ix_whale_market_candidates_condition_id",
        "polymarket_whale_market_candidates",
        ["condition_id"],
        unique=False,
    )
    op.create_index(
        "ix_whale_market_candidates_end_date",
        "polymarket_whale_market_candidates",
        ["end_date"],
        unique=False,
    )
    op.create_index(
        "ix_whale_market_candidates_last_seen_at",
        "polymarket_whale_market_candidates",
        ["last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_whale_market_candidates_last_seen_at",
        table_name="polymarket_whale_market_candidates",
    )
    op.drop_index(
        "ix_whale_market_candidates_end_date",
        table_name="polymarket_whale_market_candidates",
    )
    op.drop_index(
        "ix_whale_market_candidates_condition_id",
        table_name="polymarket_whale_market_candidates",
    )
    op.drop_table("polymarket_whale_market_candidates")
