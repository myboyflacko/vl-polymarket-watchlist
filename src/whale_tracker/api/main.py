from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, computed_field

from whale_tracker.tracker.markets.repository import (
    get_latest_market_run_id,
    list_tracked_markets,
)
from whale_tracker.tracker.whales.repository import (
    get_latest_discovery_run_id,
    list_tracked_whales,
    list_whale_observations,
)


class WhalesResponse(BaseModel):
    whales: list
    run_id: str
    filter_profile: str
    generated_at: datetime

    @computed_field
    @property
    def whales_count(self) -> int:
        return len(self.whales)


class WhaleObservationsResponse(BaseModel):
    whales: list
    run_id: str
    profile_version: str
    generated_at: datetime

    @computed_field
    @property
    def whales_count(self) -> int:
        return len(self.whales)


class MarketsResponse(BaseModel):
    markets: list
    run_id: str
    filter_profile: str
    generated_at: datetime

    @computed_field
    @property
    def markets_count(self) -> int:
        return len(self.markets)


app = FastAPI()


@app.get("/markets")
def get_latest_markets(run_id: str | None = None):
    if run_id is None:
        run_id = get_latest_market_run_id()

    if run_id is None:
        raise HTTPException(status_code=404, detail="No market run found")

    markets = list_tracked_markets(run_id=run_id)
    return MarketsResponse(
        run_id=markets.run_id,
        filter_profile=markets.filter_profile,
        generated_at=markets.generated_at,
        markets=markets.markets,
    )


@app.get("/whales")
def get_latest_whales(run_id: str | None = None):
    whales = list_tracked_whales(run_id=run_id)
    if not whales.run_id:
        raise HTTPException(status_code=404, detail="No tracked whale run found")

    return WhalesResponse(
        run_id=whales.run_id,
        filter_profile=whales.filter_profile,
        generated_at=whales.generated_at,
        whales=whales.whales,
    )


@app.get("/whale-observations")
def get_latest_whale_observations(run_id: str | None = None):
    if run_id is None:
        run_id = get_latest_discovery_run_id()

    if run_id is None:
        raise HTTPException(status_code=404, detail="No whale run found")

    whales = list_whale_observations(run_id=run_id)
    return WhaleObservationsResponse(
        run_id=run_id,
        profile_version=whales.profile_version,
        generated_at=whales.generated_at,
        whales=whales.whales,
    )
