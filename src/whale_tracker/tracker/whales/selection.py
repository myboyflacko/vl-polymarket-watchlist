from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select

from whale_tracker.tracker.whales.models import (
    PolymarketWhale,
    WhaleObservation,
    WhaleRun,
)


@dataclass(frozen=True)
class ObservedInLastRunsProfile:
    name: str = "observed_in_last_3_runs"
    required_runs: int = 3

    def wallet_statement(self) -> Select[tuple[str]]:
        latest_runs = (
            select(WhaleRun.run_id)
            .where(WhaleRun.status == "completed")
            .order_by(WhaleRun.generated_at.desc(), WhaleRun.run_id.desc())
            .limit(self.required_runs)
            .subquery()
        )
        enough_runs = select(func.count()).select_from(latest_runs).scalar_subquery()

        return (
            select(PolymarketWhale.proxy_wallet)
            .join(WhaleObservation, WhaleObservation.whale_id == PolymarketWhale.id)
            .where(WhaleObservation.run_id.in_(select(latest_runs.c.run_id)))
            .group_by(PolymarketWhale.proxy_wallet)
            .having(func.count(func.distinct(WhaleObservation.run_id)) == self.required_runs)
            .where(enough_runs == self.required_runs)
            .order_by(PolymarketWhale.proxy_wallet)
        )
