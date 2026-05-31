from __future__ import annotations

from void_liquidity.adapters.polymarket.discovery.whales.profiles import (
    TradeFirstRankingProfile,
)
from void_liquidity.adapters.polymarket.discovery.whales.repository import (
    list_latest_whales,
)
from void_liquidity.adapters.polymarket.ranking.trade_first import (
    TradeFirstRankingWeights,
    WhaleRankingResult,
    rank_trade_first_whales,
)


def select_trade_first_whales(
    *,
    profile: TradeFirstRankingProfile | None = None,
) -> WhaleRankingResult:
    whales = list_latest_whales()
    weights = TradeFirstRankingWeights.from_profile(profile) if profile else None
    return rank_trade_first_whales(whales, weights=weights)


def list_selected_whale_wallets(
    *,
    profile: TradeFirstRankingProfile | None = None,
) -> list[str]:
    ranking = select_trade_first_whales(profile=profile)
    return [ranked.whale.proxy_wallet for ranked in ranking.ranked_whales]
