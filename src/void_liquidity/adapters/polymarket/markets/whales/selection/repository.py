from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from void_liquidity.adapters.polymarket.markets.whales.discovery.domain import (
    Whale,
    Whales,
)
from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
    list_discovered_whales,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.models import (
    SelectedWhale,
    SelectedWhaleMetric,
    WhaleSelectionRun,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.profiles import (
    WhaleSelectionProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.ranking import (
    WhaleSelectionRankingResult,
)
from void_liquidity.data.engine import database_session


def get_latest_selection_run_id() -> str | None:
    with database_session() as session:
        run = session.scalar(
            select(WhaleSelectionRun)
            .order_by(
                WhaleSelectionRun.generated_at.desc(),
                WhaleSelectionRun.run_id.desc(),
            )
            .limit(1)
        )

    return run.run_id if run is not None else None


def list_selected_whale_wallets(run_id: str) -> list[str]:
    with database_session() as session:
        return list(
            session.scalars(
                select(SelectedWhaleMetric.proxy_wallet)
                .where(
                    SelectedWhaleMetric.run_id == run_id,
                    SelectedWhaleMetric.removed == 0,
                )
                .order_by(SelectedWhaleMetric.rank)
            )
        )


def list_latest_selected_whale_wallets() -> list[str]:
    latest_run_id = get_latest_selection_run_id()
    if latest_run_id is None:
        return []

    return list_selected_whale_wallets(latest_run_id)


def list_selected_whales(run_id: str) -> Whales:
    with database_session() as session:
        run = session.get(WhaleSelectionRun, run_id)
        if run is None:
            return Whales(
                whales=[],
                candidate_wallet_count=0,
                checked_wallet_count=0,
                generated_at=datetime.min.replace(tzinfo=UTC),
                profile_version="unknown",
            )
        selected_wallets = set(list_selected_whale_wallets(run_id))

    parent = list_discovered_whales(run.discovery_run_id)
    return parent.model_copy(
        update={
            "whales": [
                whale for whale in parent.whales if whale.proxy_wallet in selected_wallets
            ],
        }
    )


def persist_whale_selection_run(
    *,
    profile: WhaleSelectionProfile | None,
    run_id: str,
    discovery_run_id: str,
    generated_at: datetime,
    ranking: WhaleSelectionRankingResult,
) -> None:
    profile_payload = profile.model_dump(mode="json") if profile is not None else {}
    ranked_rows = [
        _selected_row(
            run_id=run_id,
            ranked_whale=ranked,
            rank=index,
            removed=0,
        )
        for index, ranked in enumerate(ranking.ranked_whales, start=1)
    ]
    removed_rows = [
        _selected_row(
            run_id=run_id,
            ranked_whale=ranked,
            rank=0,
            removed=1,
        )
        for ranked in ranking.removed_whales
    ]
    ranked_metric_rows = [
        _metric_row(
            run_id=run_id,
            ranked_whale=ranked,
            rank=index,
            removed=0,
            generated_at=generated_at,
        )
        for index, ranked in enumerate(ranking.ranked_whales, start=1)
    ]
    removed_metric_rows = [
        _metric_row(
            run_id=run_id,
            ranked_whale=ranked,
            rank=0,
            removed=1,
            generated_at=generated_at,
        )
        for ranked in ranking.removed_whales
    ]

    with database_session() as session:
        session.add(
            WhaleSelectionRun(
                run_id=run_id,
                discovery_run_id=discovery_run_id,
                generated_at=generated_at,
                profile=profile_payload,
                ranking_method=ranking.method,
                selected_wallet_count=len(ranking.ranked_whales),
                removed_wallet_count=len(ranking.removed_whales),
            )
        )
        _upsert_selected_whales(
            session=session,
            rows=[*ranked_rows, *removed_rows],
            seen_at=generated_at,
        )
        _upsert_metric_snapshots(
            session=session,
            rows=[*ranked_metric_rows, *removed_metric_rows],
        )
        session.commit()


def _selected_row(*, run_id: str, ranked_whale, rank: int, removed: int) -> dict:
    return {
        "proxy_wallet": ranked_whale.whale.proxy_wallet,
    }


def _metric_row(
    *,
    run_id: str,
    ranked_whale,
    rank: int,
    removed: int,
    generated_at: datetime,
) -> dict:
    whale: Whale = ranked_whale.whale
    return {
        "run_id": run_id,
        "proxy_wallet": whale.proxy_wallet,
        "rank": rank,
        "score": ranked_whale.score,
        "removed": removed,
        "metrics": whale.metrics.model_dump(mode="json"),
        "generated_at": generated_at,
    }


def _upsert_selected_whales(
    *,
    session: Session,
    rows: list[dict],
    seen_at: datetime,
) -> None:
    identity_rows = [
        {
            "proxy_wallet": row["proxy_wallet"],
            "first_seen_at": seen_at,
            "last_seen_at": seen_at,
        }
        for row in rows
    ]
    if not identity_rows:
        return

    statement = insert(SelectedWhale).values(identity_rows)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[SelectedWhale.proxy_wallet],
            set_={"last_seen_at": statement.excluded.last_seen_at},
        )
    )


def _upsert_metric_snapshots(*, session: Session, rows: list[dict]) -> None:
    if not rows:
        return

    statement = insert(SelectedWhaleMetric).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"run_id", "proxy_wallet"}
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                SelectedWhaleMetric.run_id,
                SelectedWhaleMetric.proxy_wallet,
            ],
            set_=update_columns,
        )
    )
