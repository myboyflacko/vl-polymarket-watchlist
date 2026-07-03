from __future__ import annotations

from datetime import UTC, datetime

from vl_polymarket_watchlist.core.time import ensure_utc
from vl_polymarket_watchlist.markets.discovery.strategies.whale_leaderboard import (
    WhaleDiscoverySource,
)
from vl_polymarket_watchlist.markets.domain import (
    DiscoveryRunResult,
    MarketDiscoverySource,
)
from vl_polymarket_watchlist.markets.repository import (
    complete_discovery_run,
    create_discovery_run,
    fail_discovery_run,
)
from vl_polymarket_watchlist.polymarket.client import get_polymarket_data_client


class MarketDiscoveryService:
    def __init__(
        self,
        *,
        source: MarketDiscoverySource | None = None,
    ) -> None:
        self.source = source or WhaleDiscoverySource()

    async def run(self, *, now: datetime | None = None) -> DiscoveryRunResult:
        started_at = ensure_utc(now or datetime.now(UTC))
        run_id = _build_run_id(started_at, source=self.source.source)
        create_discovery_run(
            run_id=run_id,
            source=self.source.source,
            source_version=self.source.source_version,
            started_at=started_at,
            generated_at=started_at,
            config_json=self.source.config(),
        )

        try:
            collected = await self.source.run(
                client=get_polymarket_data_client(),
                generated_at=started_at,
            )
        except Exception as exc:
            fail_discovery_run(
                run_id=run_id,
                finished_at=datetime.now(UTC),
                error_message=str(exc),
            )
            raise

        finished_at = datetime.now(UTC)
        status = "completed" if not collected.errors else "partial"
        complete_discovery_run(
            run_id=run_id,
            status=status,
            finished_at=finished_at,
            generated_at=collected.generated_at,
            checked_count=collected.checked_count,
            observations=collected.observations,
            error_count=len(collected.errors),
            error_message="; ".join(error.message for error in collected.errors) or None,
        )
        return DiscoveryRunResult(
            run_id=run_id,
            source=self.source.source,
            source_version=self.source.source_version,
            status=status,
            observations=collected.observations,
            errors=collected.errors,
            checked_count=collected.checked_count,
            observed_count=collected.observed_count,
            generated_at=collected.generated_at,
        )


def _build_run_id(generated_at: datetime, *, source: str) -> str:
    return f"{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-{source}"
