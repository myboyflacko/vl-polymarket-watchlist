from __future__ import annotations

from datetime import UTC, datetime

from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
    get_latest_discovery_run_id,
    list_discovered_whales,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.profiles import (
    WhaleSelectionProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.ranking import (
    TradeFirstRankingWeights,
    WhaleSelectionRankingResult,
    rank_trade_first_whales,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.repository import (
    list_latest_selected_whale_wallets,
    list_selected_whale_wallets,
    persist_whale_selection_run,
)


class WhaleSelectionService:
    def __init__(self, profile: WhaleSelectionProfile | None = None) -> None:
        self.profile = profile

    def run(self, *, discovery_run_id: str | None = None) -> WhaleSelectionRankingResult:
        actual_discovery_run_id = discovery_run_id or get_latest_discovery_run_id()
        if actual_discovery_run_id is None:
            return rank_trade_first_whales(
                list_discovered_whales("__missing_discovery_run__"),
            )
        whales = list_discovered_whales(actual_discovery_run_id)
        weights = (
            TradeFirstRankingWeights.from_profile(self.profile) if self.profile else None
        )
        return rank_trade_first_whales(whales, weights=weights)

    def persist(
        self,
        *,
        ranking: WhaleSelectionRankingResult,
        run_id: str,
        discovery_run_id: str,
        generated_at: datetime | None = None,
    ) -> None:
        persist_whale_selection_run(
            profile=self.profile,
            run_id=run_id,
            discovery_run_id=discovery_run_id,
            generated_at=generated_at or datetime.now(UTC),
            ranking=ranking,
        )

    def list(self, *, selection_run_id: str | None = None) -> list[str]:
        if selection_run_id is None:
            return list_latest_selected_whale_wallets()

        return list_selected_whale_wallets(selection_run_id)
