# Polymarket Storage

Polymarket Storage sammelt und speichert Polymarket-Market-Kandidaten fuer
Research- und Backtesting-Pipelines.

Das Projekt platziert keine Live-Trades, keine echten Orders und bewegt keine
Funds.

## Scope

Gespeichert werden:

- Polymarket Markets
- generische Collector-Runs
- Zuordnung, aus welchem Run ein Market kam

Nicht mehr gespeichert werden:

- Whales
- Positions
- Trades
- Python-read-only Views
- HTTP API Endpunkte

Orderbooks sind bewusst noch nicht an Collector-Runs gekoppelt. Die spaetere
Quelle ist eine Watchlist-View ausserhalb dieses Scopes.

## Market Collection

Die erste Collector-Strategy ist:

```text
leaderboard_current_positions
```

Sie nutzt nur Wallets, die sowohl im PnL-Leaderboard als auch im
Volume-Leaderboard vertreten sind. Fuer diese Wallets werden Current Positions
nur ephemeral geladen. Persistiert werden daraus ausschliesslich Markets und die
Run-Zuordnung.

## CLI

Lokale Installation:

```bash
python -m pip install -e .
```

Datenbank migrieren:

```bash
polymarket-storage init-db
```

Market Collection einmal ausfuehren:

```bash
polymarket-storage run markets
```

Explizite Strategy:

```bash
polymarket-storage run markets --strategy leaderboard_current_positions
```

Scheduler starten:

```bash
polymarket-storage schedule
```

Default-Intervall:

| Collector | Intervall |
| --- | ---: |
| markets | 900s |

Anpassung:

```bash
polymarket-storage schedule --markets-interval 900
```

## Konfiguration

Settings kommen aus Environment-Variablen oder `.env`.

Wichtige Variablen:

```text
POLYMARKET_STORAGE_POSTGRES_DB
POLYMARKET_STORAGE_POSTGRES_USER
POLYMARKET_STORAGE_POSTGRES_PASSWORD
POLYMARKET_STORAGE_POSTGRES_HOST
POLYMARKET_STORAGE_POSTGRES_PORT
POLYMARKET_STORAGE_LOG_LEVEL

POLYMARKET_DATA_API_BASE_URL
POLYMARKET_DATA_API_TIMEOUT_SECONDS
POLYMARKET_DATA_API_MAX_CONCURRENT_REQUESTS
POLYMARKET_DATA_API_REQUEST_DELAY_SECONDS
POLYMARKET_DATA_API_RATE_LIMIT_RETRY_ATTEMPTS
POLYMARKET_DATA_API_RATE_LIMIT_BACKOFF_SECONDS
POLYMARKET_DATA_API_REQUESTS_PER_SECOND
POLYMARKET_POSITIONS_REQUESTS_PER_SECOND
POLYMARKET_LEADERBOARD_REQUESTS_PER_SECOND
```

## Datenmodell

| Tabelle | Zweck |
| --- | --- |
| `polymarket_markets` | Market-/Token-Identity |
| `polymarket_collector_runs` | Generische Collector-Run-Metadaten |
| `polymarket_collector_run_markets` | Zuordnung von Markets zu Collector-Runs |

`polymarket_markets` bleibt am bisherigen Market-Shape orientiert: eine Zeile
pro `token_id` mit `condition_id`, `outcome`, `opposite_token_id` und
`opposite_outcome`.

## Entwicklung

Tests:

```bash
pytest
```

Ruff:

```bash
ruff check .
```

Integrationstests gegen PostgreSQL brauchen eine Test-Datenbank. Der Datenbankname
muss `test` enthalten:

```bash
POLYMARKET_STORAGE_TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/polymarket_storage_test pytest
```

## Projektstruktur

```text
src/polymarket_storage/cli.py                 CLI und Scheduler
src/polymarket_storage/core/db/               SQLAlchemy, Alembic
src/polymarket_storage/polymarket/            Polymarket API Client und Params
src/polymarket_storage/market_acquisition/    Market Collector Strategies
tests/                                        Unit- und Integrationstests
```
