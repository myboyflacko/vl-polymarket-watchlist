"""Baseline schema.

Revision ID: 20260611_0001
Revises:
Create Date: 2026-06-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260611_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "polymarket_conditions",
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("question", sa.String(), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("enable_order_book", sa.Boolean(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("tags", JSONB, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_latest_payload", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("condition_id"),
    )
    op.create_table(
        "polymarket_tokens",
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("outcome_index", sa.Integer(), nullable=True),
        sa.Column("opposite_token_id", sa.String(), nullable=True),
        sa.Column("opposite_outcome", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("enable_order_book", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["condition_id"],
            ["polymarket_conditions.condition_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_id"),
    )
    op.create_index(
        "ix_polymarket_tokens_condition_id",
        "polymarket_tokens",
        ["condition_id"],
    )

    op.create_table(
        "market_discovery_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_json", JSONB, nullable=False),
        sa.Column("input_refs_json", JSONB, nullable=False),
        sa.Column("checked_count", sa.Integer(), nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "market_discovery_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("event_slug", sa.String(), nullable=True),
        sa.Column("event_title", sa.String(), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("enable_order_book", sa.Boolean(), nullable=False),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("liquidity", sa.Numeric(), nullable=True),
        sa.Column("open_interest", sa.Numeric(), nullable=True),
        sa.Column("last_trade_price", sa.Numeric(), nullable=True),
        sa.Column("outcome_price", sa.Numeric(), nullable=True),
        sa.Column("source_reason", sa.String(), nullable=True),
        sa.Column("source_score", sa.Numeric(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("raw_payload", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["market_discovery_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        CREATE INDEX ix_market_discovery_observations_source_observed
        ON market_discovery_observations(source, observed_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_market_discovery_observations_token_observed
        ON market_discovery_observations(token_id, observed_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_market_discovery_observations_condition_observed
        ON market_discovery_observations(condition_id, observed_at DESC)
        """
    )
    op.create_index(
        "ix_market_discovery_observations_run_id",
        "market_discovery_observations",
        ["run_id"],
    )

    op.create_table(
        "manual_watchlist_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("condition_id", sa.String(), nullable=True),
        sa.Column("token_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("collect_orderbook", sa.Boolean(), nullable=False),
        sa.Column("collect_trades", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "market_exclusions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("condition_id", sa.String(), nullable=True),
        sa.Column("token_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "orderbook_collection_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("watchlist_version", sa.String(), nullable=False),
        sa.Column("selected_token_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("config_json", JSONB, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "orderbook_collection_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("priority", sa.String(), nullable=True),
        sa.Column("sources", JSONB, nullable=False),
        sa.Column("watchlist_reason", sa.String(), nullable=True),
        sa.Column("days_to_expiry", sa.Numeric(), nullable=True),
        sa.Column("collect_orderbook", sa.Boolean(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["orderbook_collection_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orderbook_collection_items_run_id",
        "orderbook_collection_items",
        ["run_id"],
    )
    op.create_index(
        "ix_orderbook_collection_items_token_id",
        "orderbook_collection_items",
        ["token_id"],
    )

    op.create_table(
        "orderbook_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("condition_id", sa.String(), nullable=False),
        sa.Column("token_id", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exchange_timestamp_raw", sa.String(), nullable=True),
        sa.Column("best_bid", sa.Numeric(), nullable=True),
        sa.Column("best_ask", sa.Numeric(), nullable=True),
        sa.Column("midpoint", sa.Numeric(), nullable=True),
        sa.Column("spread", sa.Numeric(), nullable=True),
        sa.Column("last_trade_price", sa.Numeric(), nullable=True),
        sa.Column("bid_depth_top_1", sa.Numeric(), nullable=True),
        sa.Column("ask_depth_top_1", sa.Numeric(), nullable=True),
        sa.Column("bid_depth_top_3", sa.Numeric(), nullable=True),
        sa.Column("ask_depth_top_3", sa.Numeric(), nullable=True),
        sa.Column("bid_depth_top_5", sa.Numeric(), nullable=True),
        sa.Column("ask_depth_top_5", sa.Numeric(), nullable=True),
        sa.Column("bid_levels_count", sa.Integer(), nullable=False),
        sa.Column("ask_levels_count", sa.Integer(), nullable=False),
        sa.Column("min_order_size", sa.Numeric(), nullable=True),
        sa.Column("tick_size", sa.Numeric(), nullable=True),
        sa.Column("negative_risk", sa.Boolean(), nullable=True),
        sa.Column("bids", JSONB, nullable=False),
        sa.Column("asks", JSONB, nullable=False),
        sa.Column("book_hash", sa.String(), nullable=True),
        sa.Column("valid_orderbook", sa.Boolean(), nullable=False),
        sa.Column("invalid_reason", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(), nullable=False),
        sa.Column("api_status", sa.Integer(), nullable=True),
        sa.Column("api_error", sa.Text(), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["orderbook_collection_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        CREATE INDEX ix_orderbook_snapshots_token_generated
        ON orderbook_snapshots(token_id, generated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_orderbook_snapshots_condition_generated
        ON orderbook_snapshots(condition_id, generated_at DESC)
        """
    )
    op.create_index("ix_orderbook_snapshots_run_id", "orderbook_snapshots", ["run_id"])
    op.execute(
        """
        CREATE INDEX ix_orderbook_snapshots_valid_generated
        ON orderbook_snapshots(valid_orderbook, generated_at DESC)
        """
    )
    _create_watchlist_view()


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS polymarket_watchlist_v")
    op.drop_index(
        "ix_orderbook_snapshots_valid_generated",
        table_name="orderbook_snapshots",
    )
    op.drop_index("ix_orderbook_snapshots_run_id", table_name="orderbook_snapshots")
    op.drop_index(
        "ix_orderbook_snapshots_condition_generated",
        table_name="orderbook_snapshots",
    )
    op.drop_index(
        "ix_orderbook_snapshots_token_generated",
        table_name="orderbook_snapshots",
    )
    op.drop_table("orderbook_snapshots")
    op.drop_index(
        "ix_orderbook_collection_items_token_id",
        table_name="orderbook_collection_items",
    )
    op.drop_index(
        "ix_orderbook_collection_items_run_id",
        table_name="orderbook_collection_items",
    )
    op.drop_table("orderbook_collection_items")
    op.drop_table("orderbook_collection_runs")
    op.drop_table("market_exclusions")
    op.drop_table("manual_watchlist_items")
    op.drop_index(
        "ix_market_discovery_observations_run_id",
        table_name="market_discovery_observations",
    )
    op.drop_index(
        "ix_market_discovery_observations_condition_observed",
        table_name="market_discovery_observations",
    )
    op.drop_index(
        "ix_market_discovery_observations_token_observed",
        table_name="market_discovery_observations",
    )
    op.drop_index(
        "ix_market_discovery_observations_source_observed",
        table_name="market_discovery_observations",
    )
    op.drop_table("market_discovery_observations")
    op.drop_table("market_discovery_runs")
    op.drop_index("ix_polymarket_tokens_condition_id", table_name="polymarket_tokens")
    op.drop_table("polymarket_tokens")
    op.drop_table("polymarket_conditions")


def _create_watchlist_view() -> None:
    op.execute(
        """
        CREATE VIEW polymarket_watchlist_v AS
        WITH observation_agg AS (
            SELECT
                token_id,
                jsonb_agg(DISTINCT source ORDER BY source) AS sources,
                count(DISTINCT source) AS source_count,
                min(observed_at) AS first_discovered_at,
                max(observed_at) AS last_discovered_at,
                (array_agg(event_slug ORDER BY observed_at DESC))[1] AS event_slug,
                (array_agg(event_title ORDER BY observed_at DESC))[1] AS event_title,
                bool_or(source = 'gamma_active') AS seen_by_gamma,
                bool_or(source = 'whale_discovery') AS seen_by_whale
            FROM market_discovery_observations
            WHERE observed_at >= now() - interval '30 days'
            GROUP BY token_id
        )
        SELECT
            c.condition_id,
            t.token_id,
            c.slug,
            c.title,
            t.outcome,
            c.event_id,
            oa.event_slug,
            oa.event_title,
            (c.active AND t.active) AS active,
            (c.closed OR t.closed) AS closed,
            c.archived,
            (c.enable_order_book AND t.enable_order_book) AS enable_order_book,
            c.end_date,
            extract(epoch FROM (c.end_date - now())) / 3600 AS hours_to_expiry,
            extract(epoch FROM (c.end_date - now())) / 86400 AS days_to_expiry,
            COALESCE(oa.sources, '[]'::jsonb) AS sources,
            COALESCE(oa.source_count, 0) AS source_count,
            oa.first_discovered_at,
            oa.last_discovered_at,
            COALESCE(oa.seen_by_gamma, false) AS seen_by_gamma,
            COALESCE(oa.seen_by_whale, false) AS seen_by_whale,
            COALESCE(manual.seen_manual, false) AS seen_manual,
            COALESCE(manual.pinned, false) AS pinned,
            COALESCE(manual.priority, 'medium') AS priority,
            CASE
                WHEN COALESCE(manual.pinned, false) THEN true
                WHEN COALESCE(exclusion.excluded, false) THEN false
                WHEN NOT (c.active AND t.active) THEN false
                WHEN (c.closed OR t.closed) THEN false
                WHEN c.archived THEN false
                WHEN NOT (c.enable_order_book AND t.enable_order_book) THEN false
                WHEN c.end_date IS NULL THEN false
                WHEN c.end_date <= now() THEN false
                WHEN c.end_date <= now() + interval '1 day' THEN false
                WHEN c.end_date >= now() + interval '180 days' THEN false
                WHEN COALESCE(oa.source_count, 0) < 1
                     AND NOT COALESCE(manual.seen_manual, false) THEN false
                ELSE true
            END AS collect_orderbook,
            CASE
                WHEN COALESCE(manual.pinned, false) THEN COALESCE(manual.collect_trades, false)
                ELSE false
            END AS collect_trades,
            CASE
                WHEN COALESCE(manual.pinned, false) THEN 'manual_pinned'
                WHEN COALESCE(exclusion.excluded, false) THEN 'excluded'
                WHEN NOT (c.active AND t.active) THEN 'not_active'
                WHEN (c.closed OR t.closed) THEN 'closed'
                WHEN c.archived THEN 'archived'
                WHEN NOT (c.enable_order_book AND t.enable_order_book) THEN 'orderbook_disabled'
                WHEN c.end_date IS NULL THEN 'missing_end_date'
                WHEN c.end_date <= now() THEN 'expired'
                WHEN c.end_date <= now() + interval '1 day' THEN 'too_close_to_expiry'
                WHEN c.end_date >= now() + interval '180 days' THEN 'too_far_from_expiry'
                WHEN COALESCE(oa.source_count, 0) > 1 THEN 'multi_source_discovery'
                WHEN COALESCE(oa.seen_by_whale, false) THEN 'whale_discovered'
                WHEN COALESCE(oa.seen_by_gamma, false) THEN 'gamma_active'
                WHEN COALESCE(manual.seen_manual, false) THEN 'manual'
                ELSE 'not_discovered'
            END AS watchlist_reason
        FROM polymarket_tokens t
        JOIN polymarket_conditions c ON c.condition_id = t.condition_id
        LEFT JOIN observation_agg oa ON oa.token_id = t.token_id
        LEFT JOIN LATERAL (
            SELECT
                count(*) > 0 AS seen_manual,
                bool_or(pinned) AS pinned,
                bool_or(collect_trades) AS collect_trades,
                CASE
                    WHEN bool_or(priority = 'high') THEN 'high'
                    WHEN bool_or(priority = 'medium') THEN 'medium'
                    ELSE 'low'
                END AS priority
            FROM manual_watchlist_items item
            WHERE (item.expires_at IS NULL OR item.expires_at > now())
              AND (
                    (item.scope = 'token' AND item.token_id = t.token_id)
                 OR (item.scope = 'condition' AND item.condition_id = c.condition_id)
                 OR (item.scope = 'slug' AND item.slug = c.slug)
              )
        ) manual ON true
        LEFT JOIN LATERAL (
            SELECT true AS excluded
            FROM market_exclusions exclusion
            WHERE (exclusion.expires_at IS NULL OR exclusion.expires_at > now())
              AND (
                    exclusion.token_id = t.token_id
                 OR exclusion.condition_id = c.condition_id
                 OR exclusion.slug = c.slug
              )
            LIMIT 1
        ) exclusion ON true
        """
    )
