from fastapi import FastAPI

from whale_tracker.tracker.markets.repository import get_latest_market_run_id, list_qualified_markets
from whale_tracker.tracker.whales.repository import get_latest_discovery_run_id, list_discovered_whales


app = FastAPI()


@app.get("/markets")
def get_latest_markets():
    run_id = get_latest_market_run_id()
    markets = list_qualified_markets(run_id=run_id)
    return markets


@app.get("/whales")
def get_latest_whales():
    run_id = get_latest_discovery_run_id()
    whales = list_discovered_whales(run_id=run_id)
    return whales