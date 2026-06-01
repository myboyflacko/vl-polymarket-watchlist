from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from void_liquidity.adapters.polymarket.markets.whales.discovery.models import (
    DiscoveredWhale,
    DiscoveredWhaleMetric,
    WhaleDiscoveryRun,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.domain import (
    Whale,
    WhaleIdentity,
    WhaleMetrics,
    Whales,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.profiles import (
    WhaleDiscoveryProfile,
)
from void_liquidity.data.engine import database_session


def get_latest_discovery_run_id() -> str | None:
    with database_session() as session:
        latest_run = session.scalar(_latest_completed_run_statement())

    return latest_run.run_id if latest_run is not None else None


def list_discovered_whale_wallets(run_id: str) -> list[str]:
    with database_session() as session:
        return list(
            session.scalars(
                select(DiscoveredWhaleMetric.proxy_wallet)
                .where(DiscoveredWhaleMetric.run_id == run_id)
                .order_by(DiscoveredWhaleMetric.id)
            )
        )


def list_latest_discovered_whale_wallets() -> list[str]:
    latest_run_id = get_latest_discovery_run_id()
    if latest_run_id is None:
        return []

    return list_discovered_whale_wallets(latest_run_id)


def list_discovered_whales(run_id: str) -> Whales:
    with database_session() as session:
        run = session.get(WhaleDiscoveryRun, run_id)
        if run is None:
            return Whales(
                whales=[],
                candidate_wallet_count=0,
                checked_wallet_count=0,
                generated_at=datetime.min.replace(tzinfo=UTC),
                profile_version="unknown",
            )

        snapshots = list(
            session.scalars(
                select(DiscoveredWhaleMetric)
                .where(DiscoveredWhaleMetric.run_id == run_id)
                .order_by(DiscoveredWhaleMetric.id)
            )
        )

        return Whales(
            whales=[_whale_from_snapshot(snapshot) for snapshot in snapshots],
            candidate_wallet_count=run.candidate_wallet_count,
            checked_wallet_count=run.checked_wallet_count,
            generated_at=run.generated_at,
            profile_version=run.profile_version,
        )


def list_latest_discovered_whales() -> Whales:
    latest_run_id = get_latest_discovery_run_id()
    if latest_run_id is None:
        return Whales(
            whales=[],
            candidate_wallet_count=0,
            checked_wallet_count=0,
            generated_at=datetime.min.replace(tzinfo=UTC),
            profile_version="unknown",
        )

    return list_discovered_whales(latest_run_id)


def persist_whale_discovery_run(
    *,
    profile: WhaleDiscoveryProfile,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    generated_at: datetime,
    whales: Whales,
) -> None:
    with database_session() as session:
        session.add(
            WhaleDiscoveryRun(
                run_id=run_id,
                profile_version=profile.profile_version,
                status="completed",
                started_at=started_at,
                finished_at=finished_at,
                generated_at=generated_at,
                candidate_wallet_count=whales.candidate_wallet_count,
                checked_wallet_count=whales.checked_wallet_count,
                accepted_wallet_count=len(whales.whales),
                profile=profile.model_dump(mode="json"),
            )
        )
        session.flush()
        _upsert_discovered_whales(
            session=session,
            seen_at=generated_at,
            whales=whales.whales,
        )
        _upsert_metric_snapshots(
            session=session,
            run_id=run_id,
            generated_at=generated_at,
            whales=whales.whales,
        )
        session.commit()


def _upsert_discovered_whales(
    *,
    session: Session,
    seen_at: datetime,
    whales: Iterable[Whale],
) -> None:
    rows = [
        {
            "proxy_wallet": whale.proxy_wallet,
            "identity": whale.identity.model_dump(mode="json"),
            "first_seen_at": seen_at,
            "last_seen_at": seen_at,
        }
        for whale in whales
    ]

    if not rows:
        return

    statement = insert(DiscoveredWhale).values(rows)
    update_columns = {
        "identity": statement.excluded.identity,
        "last_seen_at": statement.excluded.last_seen_at,
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[DiscoveredWhale.proxy_wallet],
            set_=update_columns,
        )
    )


def _upsert_metric_snapshots(
    *,
    session: Session,
    run_id: str,
    generated_at: datetime,
    whales: Iterable[Whale],
) -> None:
    rows = [
        {
            "run_id": run_id,
            "proxy_wallet": whale.proxy_wallet,
            "metrics": whale.metrics.model_dump(mode="json"),
            "collection_quality": whale.metrics.collection_quality.model_dump(
                mode="json"
            ),
            "generated_at": generated_at,
        }
        for whale in whales
    ]

    if not rows:
        return

    statement = insert(DiscoveredWhaleMetric).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "proxy_wallet"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                DiscoveredWhaleMetric.run_id,
                DiscoveredWhaleMetric.proxy_wallet,
            ],
            set_=update_columns,
        )
    )


def _latest_completed_run_statement():
    return (
        select(WhaleDiscoveryRun)
        .where(WhaleDiscoveryRun.status == "completed")
        .order_by(
            WhaleDiscoveryRun.generated_at.desc(),
            WhaleDiscoveryRun.run_id.desc(),
        )
        .limit(1)
    )


def _whale_from_snapshot(snapshot: DiscoveredWhaleMetric) -> Whale:
    metrics = dict(snapshot.metrics)
    metrics.pop("ranking", None)
    return Whale(
        identity=WhaleIdentity(proxy_wallet=snapshot.proxy_wallet),
        metrics=WhaleMetrics.model_validate(metrics),
    )
