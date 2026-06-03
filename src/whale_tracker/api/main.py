from fastapi import FastAPI

from whale_tracker.tracker.markets.repository import get_latest_market_run_id, list_markets



app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/markets")
def get_latest_markets():
    run_id = get_latest_market_run_id()
    data = list_markets(run_id=run_id)
    return data