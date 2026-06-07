# Whale Tracker

Whale Tracker is a Polymarket tracking service that discovers high-signal wallets,
collects their trading and position metrics, filters and scores them, and then
uses the selected wallets to find markets where multiple whales are currently
positioned.

The project is intentionally split into two tracking domains:

- `whales`: find and rank relevant Polymarket wallets.
- `markets`: find and rank markets based on the positions held by selected whales.

Data is collected from Polymarket APIs and persisted to PostgreSQL through
SQLAlchemy.

## Main Components

### `src/whale_tracker/cli.py`

The CLI is the runtime entrypoint exposed as `whale-tracker`.

Commands:

```bash
whale-tracker init-db
whale-tracker run whales
whale-tracker run markets
whale-tracker run all
whale-tracker schedule
whale-tracker api
```

Important options:

- `--no-scoring`: disables scoring where a scoring profile is registered.
- `--market-limit`: limits persisted scored markets when market scoring is enabled.
- `--whales-run-id`: runs market tracking against a specific whale selection run.
- `--whales-interval`: scheduler interval for whale runs, default `3600` seconds.
- `--markets-interval`: scheduler interval for market runs, default `900` seconds.
- `api --host`: API server host, default `127.0.0.1`.
- `api --port`: API server port, default `8000`.
- `api --no-reload`: disables local auto-reload.

`run all` first runs whale tracking, then passes that whale run id into market
tracking.

## HTTP API

The FastAPI app exposes compact read endpoints for the latest persisted runs.

Start the API locally:

```bash
whale-tracker api
```

This starts a local Uvicorn server for `whale_tracker.api.main:app`. The command
runs in the foreground until stopped with `Ctrl+C`.

Endpoints:

- `GET /whales`: returns the selected whales for the latest completed whale run.
- `GET /markets`: returns the qualified markets for the latest completed market run.

Both endpoints accept an optional `run_id` query parameter:

```text
/whales?run_id=20260101T120000000000Z-whales
/markets?run_id=20260101T120000000000Z-markets
```

If no `run_id` is provided, the latest completed run is used. If no matching run
exists, the endpoint returns `404`.

## Docker

The Docker setup uses one image with separate Compose services:

- `postgres`: stores tracker state.
- `api`: starts the local HTTP API on port `8000`.
- `scheduler`: runs whale and market tracking continuously.
- `cli`: tool service for one-off commands.

Build the image:

```bash
docker compose build
```

Initialize the database:

```bash
docker compose run --rm cli init-db
```

Start the API:

```bash
docker compose up api
```

Run one-off tracker commands:

```bash
docker compose run --rm cli run whales
docker compose run --rm cli run markets
```

Start the scheduler:

```bash
docker compose up scheduler
```

The Compose services use the named `postgres-data` volume for database state.
Application logs are emitted as JSON lines to stdout and can be inspected through
Docker logs, for example with `docker compose logs api` or
`docker compose logs scheduler`.

### `src/whale_tracker/settings.py`

Settings are Pydantic settings loaded from environment variables and `.env`.

Main settings groups:

- `PolymarketDataApiClientSettings`: Data API base URL, timeout, concurrency,
  request delay, retry/backoff and per-endpoint rate limits.
- `DatabaseSettings`: PostgreSQL connection fields used to build the internal
  SQLAlchemy database URL.
- `LoggingSettings`: JSON stdout log level.

Internal database URL format:

```text
postgresql+psycopg://USER:PASSWORD@HOST:PORT/DB
```

Useful environment variables:

- `WHALE_TRACKER_POSTGRES_DB`
- `WHALE_TRACKER_POSTGRES_USER`
- `WHALE_TRACKER_POSTGRES_PASSWORD`
- `WHALE_TRACKER_POSTGRES_HOST`
- `WHALE_TRACKER_POSTGRES_PORT`
- `WHALE_TRACKER_LOG_LEVEL`
- `POLYMARKET_DATA_API_BASE_URL`
- `POLYMARKET_DATA_API_TIMEOUT_SECONDS`
- `POLYMARKET_DATA_API_MAX_CONCURRENT_REQUESTS`
- `POLYMARKET_DATA_API_REQUEST_DELAY_SECONDS`
- `POLYMARKET_DATA_API_RATE_LIMIT_RETRY_ATTEMPTS`
- `POLYMARKET_DATA_API_RATE_LIMIT_BACKOFF_SECONDS`
- `POLYMARKET_DATA_API_REQUESTS_PER_SECOND`
- `POLYMARKET_TRADES_REQUESTS_PER_SECOND`
- `POLYMARKET_POSITIONS_REQUESTS_PER_SECOND`
- `POLYMARKET_LEADERBOARD_REQUESTS_PER_SECOND`

### `src/whale_tracker/core/logging.py`

Logging is configured by `configure_logging()` and emits JSON lines to stdout.

Current behavior:

- writes one JSON object per line to stdout
- supports `DEBUG`, `INFO`, `WARNING`, `ERROR` and `CRITICAL`
- reduces `httpx` and `httpcore` log noise to `WARNING`
- is idempotent for the same level

### `src/whale_tracker/tracker/whales`

The whale tracker discovers candidate wallets, collects wallet metrics, filters
them, scores them, and persists the selected wallets.

Key files:

- `service.py`: orchestrates discovery, filtering, scoring and persistence.
- `discovery.py`: defines the discovery profile.
- `helpers.py`: fetches leaderboards, trades and current positions, then aggregates
  metrics.
- `filter.py`: contains the default whale filter profile.
- `scoring.py`: contains whale scoring profiles.
- `domain.py`: Pydantic domain models for wallets, metrics, filter results and
  scoring results.
- `repository.py`: persists runs, wallet identities and metric snapshots.

### `src/whale_tracker/tracker/markets`

The market tracker starts from selected whale wallets, collects their open
positions, groups positions into market candidates, filters markets, optionally
scores them, and persists market snapshots.

Key files:

- `service.py`: orchestrates market discovery, filtering, optional scoring and
  persistence.
- `discovery.py`: loads selected whale wallets and collects their current
  positions.
- `helpers.py`: fetches and normalizes wallet positions.
- `filter.py`: groups positions by token and applies the default market filter.
- `scoring.py`: contains the market scoring profile.
- `domain.py`: Pydantic domain models for positions, markets and run results.
- `repository.py`: persists market identities, run metadata and metric snapshots.

## Discovery, Filtering And Scoring Architecture

Both domains follow the same pipeline:

```text
discovery -> filter -> scoring -> persistence
```

Discovery produces raw domain objects:

- Whale discovery produces `Whales`.
- Market discovery produces `Markets`.

Filtering removes objects that do not meet hard eligibility rules:

- Whale filtering produces `FilteredWhales`.
- Market filtering produces `FilteredMarkets`.

Scoring ranks the filtered objects and may remove low-ranked entries:

- Whale scoring produces `ScoredWhales`.
- Market scoring produces `ScoredMarkets`.

Persistence stores the final selected entries. If scoring is disabled or absent,
the filtered entries are persisted with score `0.0`.

## Whale Discovery

Current whale discovery profile:

```text
profile_version = whale_discovery_trade_first
wallet_count = 250
wallet_batch_size = 4
leaderboard_category = OVERALL
leaderboard_time_period = MONTH
leaderboard_limit = 50
trade_window_days = 30
recent_window_days = 7
trade_limit = 500
max_trade_pages_per_wallet = 20
taker_only = true
current_positions_limit = 500
current_positions_market_chunk_size = 50
```

Discovery works like this:

1. Fetch Polymarket leaderboard pages ordered by monthly PnL.
2. Fetch Polymarket leaderboard pages ordered by monthly volume.
3. Merge wallets from both leaderboards.
4. For each candidate wallet, collect recent trades.
5. Aggregate 30-day and 7-day trade metrics.
6. Collect current positions for markets touched by recent trades.
7. Aggregate exposure metrics.

The resulting whale metrics include:

- leaderboard PnL and volume
- PnL rank and volume rank
- candidate source: `pnl`, `volume` or `both`
- 30-day and 7-day trade count
- 30-day and 7-day trade volume
- last trade age
- buy/sell volume and net flow
- unique traded markets
- market concentration
- current position value
- open position count
- position concentration
- collection quality flags

## Whale Filter Profile

Current default profile:

```text
name = default_whale_filter
min_trade_count_30d = 0
min_current_position_value = 0.0
```

A whale is kept when:

```text
trade_count_30d >= min_trade_count_30d
and current_position_value >= min_current_position_value
```

With the current defaults, this filter is intentionally permissive. It mainly
keeps the pipeline shape stable while the scoring profile performs the meaningful
selection.

## Whale Scoring Profiles

### Default: `trade_first_zscore_v1`

The default whale service registers `ZScoreWhaleScoringProfile`.

Default weights:

```text
pnl_weight = 0.30
volume_weight = 0.25
trade_activity_weight = 0.20
recency_weight = 0.15
exposure_weight = 0.10
concentration_penalty_weight = 0.10
score_scale = 2.0
min_score = 50.0
```

Scoring uses current-run Z-scores for:

- monthly leaderboard PnL
- monthly leaderboard volume
- 30-day trade volume
- last trade age, where lower is better
- current position value
- 30-day market concentration
- current position concentration

The positive signals are combined as a weighted mean. Concentration is applied as
a penalty using the larger positive Z-score of market concentration or position
concentration. Below-average concentration does not create a bonus.

The raw score is converted to a `0..100` score with a sigmoid function. Wallets
with `score > min_score` are selected. Wallets with `score <= min_score` are
removed.

### Alternative: `trade_first_percentile_v1`

`PercentileWhaleScoringProfile` is available but not the default.

It scores the same signals with percentile ranks instead of Z-scores and cuts the
bottom percentile:

```text
bottom_cut_percentile = 0.75
```

With the default value, only the top 25 percent of filtered whales are kept.

## Market Discovery

Market discovery depends on a whale selection run.

If `whales_run_id` is provided, that run is used. Otherwise, the latest completed
whale selection run is used.

Discovery works like this:

1. Load selected whale wallets from the whale repository.
2. Fetch current positions for each selected wallet.
3. Normalize each position into `WhalePosition`.
4. Return all collected positions plus collection errors.

Positions include token id, condition id, outcome, market title, slug, size,
current value, average price, current price, opposite token data, end date and
negative-risk flag.

## Market Filter Profile

Current default profile:

```text
name = default_market_filter
min_whale_count = 3
```

Filtering works like this:

1. Group all whale positions by `token_id`.
2. Build one `Market` candidate per token.
3. Count unique whale wallets per token.
4. Keep markets where `whale_count >= min_whale_count`.
5. Sort kept markets by `whale_count` and `total_current_value`, descending.

For each market candidate, the filter calculates:

- unique whale wallet count
- total position size
- total current value
- weighted average entry price
- current price
- wallet list
- opposite token and outcome metadata

## Market Scoring Profile

Available profile:

```text
name = market_zscore_v1
whale_count_weight = 1.0
total_current_value_weight = 1.0
value_per_wallet_weight = 1.0
bottom_cut_percentile = 0.75
score_scale = 2.0
```

Market scoring uses current-run Z-scores for:

- whale count
- total current value
- value per wallet

The weighted mean is converted to a `0..100` score with a sigmoid function.
Markets are ranked by score, whale count and total current value. The bottom
percentile is removed; with the current default, the top 25 percent are kept.
`--market-limit` can further cap the number of persisted scored markets.

Scoring also enriches selected markets with:

- `qualified = true`
- `score`
- `price_delta = cur_price - weighted_avg_price`
- `price_delta_pct`
- `value_per_wallet`

Important current behavior: `ZScoreMarketScoringProfile` exists and is
registerable, but `MarketTrackerService` does not register it by default. The CLI
therefore currently persists filtered markets unless market scoring is registered
programmatically.

## Development

Install the package in editable mode:

```bash
python -m pip install -e .
```

Initialize the default database:

```bash
whale-tracker init-db
```

`init-db` runs Alembic migrations against the PostgreSQL URL built from
`WHALE_TRACKER_POSTGRES_*`.

Run tests:

```bash
pytest
```

Database integration tests require a PostgreSQL database URL whose database name
contains `test`:

```bash
WHALE_TRACKER_TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/whale_tracker_test pytest
```

Run Ruff:

```bash
ruff check .
```
