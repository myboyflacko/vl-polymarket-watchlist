from __future__ import annotations

from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
    list_latest_whales,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.profiles import (
    WhaleSelectionProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.ranking import (
    TradeFirstRankingWeights,
    WhaleSelectionRankingResult,
    rank_trade_first_whales,
)


class WhaleSelectionService:
    def __init__(self, profile: WhaleSelectionProfile | None = None) -> None:
        self.profile = profile

    def select(self) -> WhaleSelectionRankingResult:
        whales = list_latest_whales()
        weights = (
            TradeFirstRankingWeights.from_profile(self.profile) if self.profile else None
        )
        return rank_trade_first_whales(whales, weights=weights)

    def wallets(self) -> list[str]:
        ranking = self.select()
        return [ranked.whale.proxy_wallet for ranked in ranking.ranked_whales]
