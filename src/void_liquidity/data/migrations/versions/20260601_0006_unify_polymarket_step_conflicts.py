"""unify polymarket step conflict policies

Revision ID: 20260601_0006
Revises: 20260601_0005
Create Date: 2026-06-01 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
import json

from alembic import op
import sqlalchemy as sa


revision: str = "20260601_0006"
down_revision: str | Sequence[str] | None = "20260601_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _rebuild_discovered_whales()
    _dedupe_discovery_metrics()
    _dedupe_selection_metrics()
    _rebuild_selected_whales()
    _rebuild_qualified_markets()


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for the unified step schema")


def _rebuild_discovered_whales() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT proxy_wallet, identity, generated_at
            FROM polymarket_discovered_whales
            ORDER BY generated_at, id
            """
        )
    ).mappings()
    identities: dict[str, dict] = {}
    for row in rows:
        wallet = row["proxy_wallet"]
        generated_at = row["generated_at"]
        current = identities.get(wallet)
        if current is None:
            identities[wallet] = {
                "proxy_wallet": wallet,
                "identity": row["identity"],
                "first_seen_at": generated_at,
                "last_seen_at": generated_at,
            }
            continue
        current["last_seen_at"] = generated_at
        current["identity"] = row["identity"]

    op.drop_index("ux_discovered_whales_run_wallet", table_name="polymarket_discovered_whales")
    op.drop_index("ix_discovered_whales_proxy_wallet", table_name="polymarket_discovered_whales")
    op.drop_table("polymarket_discovered_whales")
    op.create_table(
        "polymarket_discovered_whales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proxy_wallet", sa.String(), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_discovered_whales_proxy_wallet",
        "polymarket_discovered_whales",
        ["proxy_wallet"],
        unique=True,
    )
    if identities:
        connection.execute(
            sa.table(
                "polymarket_discovered_whales",
                sa.column("proxy_wallet"),
                sa.column("identity"),
                sa.column("first_seen_at"),
                sa.column("last_seen_at"),
            ).insert(),
            list(identities.values()),
        )


def _dedupe_discovery_metrics() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM polymarket_discovered_whale_metrics
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM polymarket_discovered_whale_metrics
                GROUP BY run_id, proxy_wallet
            )
            """
        )
    )
    op.drop_index(
        "ix_discovered_whale_metrics_run_wallet",
        table_name="polymarket_discovered_whale_metrics",
    )
    op.create_index(
        "ux_discovered_whale_metrics_run_wallet",
        "polymarket_discovered_whale_metrics",
        ["run_id", "proxy_wallet"],
        unique=True,
    )


def _rebuild_selected_whales() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT selected.proxy_wallet, runs.generated_at
            FROM polymarket_selected_whales AS selected
            JOIN polymarket_whale_selection_runs AS runs ON runs.run_id = selected.run_id
            ORDER BY runs.generated_at, selected.id
            """
        )
    ).mappings()
    identities: dict[str, dict] = {}
    for row in rows:
        wallet = row["proxy_wallet"]
        generated_at = row["generated_at"]
        current = identities.get(wallet)
        if current is None:
            identities[wallet] = {
                "proxy_wallet": wallet,
                "first_seen_at": generated_at,
                "last_seen_at": generated_at,
            }
            continue
        current["last_seen_at"] = generated_at

    op.drop_index("ux_selected_whales_run_wallet", table_name="polymarket_selected_whales")
    op.drop_table("polymarket_selected_whales")
    op.create_table(
        "polymarket_selected_whales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proxy_wallet", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_selected_whales_proxy_wallet",
        "polymarket_selected_whales",
        ["proxy_wallet"],
        unique=True,
    )
    if identities:
        connection.execute(
            sa.table(
                "polymarket_selected_whales",
                sa.column("proxy_wallet"),
                sa.column("first_seen_at"),
                sa.column("last_seen_at"),
            ).insert(),
            list(identities.values()),
        )


def _dedupe_selection_metrics() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("polymarket_selected_whale_metrics") as batch_op:
        batch_op.add_column(sa.Column("removed", sa.Integer(), nullable=False, server_default="0"))
    connection.execute(
        sa.text(
            """
            UPDATE polymarket_selected_whale_metrics
            SET removed = COALESCE((
                SELECT selected.removed
                FROM polymarket_selected_whales AS selected
                WHERE selected.proxy_wallet = polymarket_selected_whale_metrics.proxy_wallet
                LIMIT 1
            ), 0)
            """
        )
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM polymarket_selected_whale_metrics
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM polymarket_selected_whale_metrics
                GROUP BY run_id, proxy_wallet
            )
            """
        )
    )
    op.drop_index(
        "ix_selected_whale_metrics_run_wallet",
        table_name="polymarket_selected_whale_metrics",
    )
    op.create_index(
        "ux_selected_whale_metrics_run_wallet",
        "polymarket_selected_whale_metrics",
        ["run_id", "proxy_wallet"],
        unique=True,
    )


def _rebuild_qualified_markets() -> None:
    connection = op.get_bind()
    old_rows = list(
        connection.execute(
            sa.text(
                """
                SELECT run_id, token_id, profile_name, rank, score, price_delta,
                       price_delta_pct, value_per_wallet, candidate, generated_at
                FROM polymarket_qualified_markets
                ORDER BY generated_at, id
                """
            )
        ).mappings()
    )

    op.drop_index(
        "ux_qualified_markets_run_token_profile",
        table_name="polymarket_qualified_markets",
    )
    op.drop_table("polymarket_qualified_markets")
    op.create_table(
        "polymarket_qualified_markets",
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
        "ux_qualified_markets_token_id",
        "polymarket_qualified_markets",
        ["token_id"],
        unique=True,
    )
    op.create_index(
        "ix_qualified_markets_condition_id",
        "polymarket_qualified_markets",
        ["condition_id"],
        unique=False,
    )
    op.create_index(
        "ix_qualified_markets_end_date",
        "polymarket_qualified_markets",
        ["end_date"],
        unique=False,
    )
    op.create_table(
        "polymarket_qualified_market_metric_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("token_id", sa.String(), nullable=False),
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
            ["token_id"],
            ["polymarket_qualified_markets.token_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_qualified_market_metric_snapshots_run_token_profile",
        "polymarket_qualified_market_metric_snapshots",
        ["run_id", "token_id", "profile_name"],
        unique=True,
    )
    op.create_index(
        "ix_qualified_market_metric_snapshots_token_id",
        "polymarket_qualified_market_metric_snapshots",
        ["token_id"],
        unique=False,
    )

    identities: dict[str, dict] = {}
    snapshots: list[dict] = []
    for row in old_rows:
        candidate = _candidate_payload(row["candidate"])
        generated_at = row["generated_at"]
        token_id = row["token_id"]
        identity = identities.get(token_id)
        if identity is None:
            identities[token_id] = _qualified_identity_row(
                token_id=token_id,
                candidate=candidate,
                generated_at=generated_at,
            )
        else:
            identity["last_seen_at"] = generated_at
            _update_qualified_identity(identity=identity, candidate=candidate)
        snapshots.append(
            {
                "run_id": row["run_id"],
                "token_id": token_id,
                "profile_name": row["profile_name"],
                "rank": row["rank"],
                "score": row["score"],
                "price_delta": row["price_delta"],
                "price_delta_pct": row["price_delta_pct"],
                "value_per_wallet": row["value_per_wallet"],
                "candidate": candidate,
                "generated_at": generated_at,
            }
        )

    if identities:
        connection.execute(
            sa.table(
                "polymarket_qualified_markets",
                sa.column("token_id"),
                sa.column("condition_id"),
                sa.column("title"),
                sa.column("slug"),
                sa.column("outcome"),
                sa.column("opposite_token_id"),
                sa.column("opposite_outcome"),
                sa.column("end_date"),
                sa.column("negative_risk"),
                sa.column("first_seen_at"),
                sa.column("last_seen_at"),
            ).insert(),
            list(identities.values()),
        )
    if snapshots:
        connection.execute(
            sa.table(
                "polymarket_qualified_market_metric_snapshots",
                sa.column("run_id"),
                sa.column("token_id"),
                sa.column("profile_name"),
                sa.column("rank"),
                sa.column("score"),
                sa.column("price_delta"),
                sa.column("price_delta_pct"),
                sa.column("value_per_wallet"),
                sa.column("candidate"),
                sa.column("generated_at"),
            ).insert(),
            snapshots,
        )


def _candidate_payload(value) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _qualified_identity_row(
    *,
    token_id: str,
    candidate: dict,
    generated_at: datetime,
) -> dict:
    return {
        "token_id": token_id,
        "condition_id": candidate["condition_id"],
        "title": candidate["title"],
        "slug": candidate["slug"],
        "outcome": candidate["outcome"],
        "opposite_token_id": candidate.get("opposite_token_id"),
        "opposite_outcome": candidate.get("opposite_outcome"),
        "end_date": candidate.get("end_date"),
        "negative_risk": candidate.get("negative_risk", False),
        "first_seen_at": generated_at,
        "last_seen_at": generated_at,
    }


def _update_qualified_identity(*, identity: dict, candidate: dict) -> None:
    identity.update(
        {
            "condition_id": candidate["condition_id"],
            "title": candidate["title"],
            "slug": candidate["slug"],
            "outcome": candidate["outcome"],
            "opposite_token_id": candidate.get("opposite_token_id"),
            "opposite_outcome": candidate.get("opposite_outcome"),
            "end_date": candidate.get("end_date"),
            "negative_risk": candidate.get("negative_risk", False),
        }
    )
