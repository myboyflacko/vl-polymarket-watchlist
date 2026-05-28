from __future__ import annotations

from sqlalchemy import select

from void_liquidity.adapters.polymarket.discovery.whales.models import TrackedWhale
from void_liquidity.data import database_session


def list_tracked_whale_wallets() -> list[str]:
    with database_session() as session:
        return list(
            session.scalars(
                select(TrackedWhale.proxy_wallet).order_by(TrackedWhale.id)
            )
        )
