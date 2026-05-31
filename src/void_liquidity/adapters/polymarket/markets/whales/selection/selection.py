from __future__ import annotations

from void_liquidity.adapters.polymarket.markets.whales.discovery.repository import (
    list_latest_whales,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.profiles import (
    WhaleSelectionProfile,
)
from void_liquidity.adapters.polymarket.markets.whales.selection.ranking import (
    TradeFirstRankingWeights,
    WhaleRankingResult,
    rank_trade_first_whales,
)


def select_trade_first_whales(
    *,
    profile: WhaleSelectionProfile | None = None,
) -> WhaleRankingResult:
    whales = list_latest_whales()
    weights = TradeFirstRankingWeights.from_profile(profile) if profile else None
    return rank_trade_first_whales(whales, weights=weights)


def list_selected_whale_wallets(
    *,
    profile: WhaleSelectionProfile | None = None,
) -> list[str]:
    ranking = select_trade_first_whales(profile=profile)
    return [ranked.whale.proxy_wallet for ranked in ranking.ranked_whales]


class WhaleSelectionService:
    def __init__(self, profile: WhaleSelectionProfile | None = None) -> None:
        self.profile = profile

    def select(self) -> WhaleRankingResult:
        return select_trade_first_whales(profile=self.profile)

    def wallets(self) -> list[str]:
        return list_selected_whale_wallets(profile=self.profile)
