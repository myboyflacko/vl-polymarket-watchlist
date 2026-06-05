from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, computed_field

from datetime import datetime

from whale_tracker.tracker.markets.repository import (
    get_latest_market_run_id,
    list_qualified_markets,
)
from whale_tracker.tracker.whales.repository import (
    get_latest_discovery_run_id,
    list_discovered_whales,
)


class WhalesResponse(BaseModel):
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

    markets = list_qualified_markets(run_id=run_id)
    response = MarketsResponse(
        run_id=run_id,
        markets=markets,
    )
    return response


@app.get("/whales")
def get_latest_whales(run_id: str | None = None):
    if run_id is None:
        run_id = get_latest_discovery_run_id()

    if run_id is None:
        raise HTTPException(status_code=404, detail="No whale run found")

    whales = list_discovered_whales(run_id=run_id)

    response = WhalesResponse(
        run_id=run_id,
        profile_version=whales.profile_version,
        generated_at=whales.generated_at,
        whales=whales.whales,
    )
    return response
