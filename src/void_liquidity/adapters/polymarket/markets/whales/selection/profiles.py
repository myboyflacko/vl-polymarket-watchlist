from __future__ import annotations

from pydantic import BaseModel, Field


class WhaleSelectionProfile(BaseModel):
    pnl_weight: float = Field(default=0.30, ge=0)
    volume_weight: float = Field(default=0.25, ge=0)
    trade_activity_weight: float = Field(default=0.20, ge=0)
    recency_weight: float = Field(default=0.15, ge=0)
    exposure_weight: float = Field(default=0.10, ge=0)
    concentration_penalty_weight: float = Field(default=0.10, ge=0)
    bottom_cut_percentile: float = Field(default=0.25, ge=0, le=1)
