from __future__ import annotations

from pydantic import BaseModel, Field

from whale_tracker.tracker.whales.domain import (
    FilteredWhales,
    Whale,
    Whales,
)


class DefaultWhaleFilterProfile(BaseModel):
    name: str = "default_whale_filter"
    min_trade_count_30d: int = Field(default=0, ge=0)
    min_current_position_value: float = Field(default=0.0, ge=0)

    def run(self, whales: Whales) -> FilteredWhales:
        kept: list[Whale] = []
        removed: list[Whale] = []

        for whale in whales.whales:
            if _matches_profile(whale=whale, profile=self):
                kept.append(whale)
            else:
                removed.append(whale)

        return FilteredWhales(
            whales=kept,
            removed_whales=removed,
            checked_wallet_count=whales.checked_wallet_count,
            generated_at=whales.generated_at,
            profile_name=self.name,
        )


def _matches_profile(*, whale: Whale, profile: DefaultWhaleFilterProfile) -> bool:
    return (
        whale.metrics.trades.trade_count_30d >= profile.min_trade_count_30d
        and whale.metrics.exposure.current_position_value
        >= profile.min_current_position_value
    )
