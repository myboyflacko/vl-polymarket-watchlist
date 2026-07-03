# VL Polymarket Watchlist

VL Polymarket Watchlist baut ein reproduzierbares Polymarket-Collection-Universum:

```text
Discovery Sources
-> market_discovery_runs
-> market_discovery_observations
-> polymarket_conditions / polymarket_tokens
-> polymarket_watchlist_v
-> orderbook_collection_runs / orderbook_collection_items
-> orderbook_snapshots
```

Das Projekt platziert keine Live-Trades, keine echten Orders und bewegt keine
Funds.

## Scope

Gespeichert werden:

- canonical Conditions und Outcome-Tokens
- Discovery-Runs und append-only Market-Observations
- manuelle Watchlist-Inclusions und Exclusions
- Watchlist-Snapshots pro Orderbook-Collection-Run
- Orderbook-Snapshots mit Validierungsstatus

Nicht gespeichert werden:

- dauerhafte Whale-Position-Full-Snapshots
- Trade-Persistenz
- HTTP API Endpunkte

Whales sind nur eine Discovery-Quelle. Whale Discovery darf Current Positions
temporär nutzen, persistiert daraus aber nur Market-Observations.

## CLI

Lokale Installation:

```bash
python -m pip install -e .
```

Datenbank migrieren:

```bash
vl-polymarket-watchlist init-db
```

Discovery einmal ausführen:

```bash
vl-polymarket-watchlist run discovery
```

Orderbooks aus der aktiven Watchlist sammeln:

```bash
vl-polymarket-watchlist run orderbooks
```

Beides nacheinander:

```bash
vl-polymarket-watchlist run all
```

Scheduler starten:

```bash
vl-polymarket-watchlist schedule
```

Default-Intervalle:

| Collector | Intervall |
| --- | ---: |
| discovery | 900s |
| orderbooks | 300s |

Orderbooks laufen unabhängig und können deutlich häufiger getaktet werden als
Discovery. Vor jedem Orderbook-Run prüft der Collector, ob kein Discovery-Run
gerade `running` ist und ob der letzte `completed` oder `partial` Discovery-Run
maximal 24 Stunden alt ist. Wenn diese Readiness fehlt, wird ohne
`orderbook_collection_runs` Eintrag geskippt.

## Datenmodell

| Tabelle/View | Zweck |
| --- | --- |
| `polymarket_conditions` | Eine Zeile pro `condition_id` |
| `polymarket_tokens` | Eine Zeile pro handelbarem Outcome-Token |
| `market_discovery_runs` | Generische Discovery-Run-Metadaten |
| `market_discovery_observations` | Append-only Strategy-/Source-Beobachtungen |
| `manual_watchlist_items` | Manuell gepinnte oder temporär beobachtete Markets |
| `market_exclusions` | Temporäre oder dauerhafte Exclusions |
| `polymarket_watchlist_v` | Token-level Collection Universe |
| `orderbook_collection_runs` | Audit-Run der Orderbook Collection |
| `orderbook_collection_items` | Snapshot der Watchlist vor dem Fetch |
| `orderbook_snapshots` | Parsed CLOB Orderbooks und Validierung |

Orderbook Collection liest ausschließlich:

```sql
SELECT token_id
FROM polymarket_watchlist_v
WHERE collect_orderbook = true;
```

Vor jedem API-Fetch wird diese View in `orderbook_collection_items` gesnapshottet.
Backtests rekonstruieren dadurch, welcher Token wann und warum gesammelt wurde.

## Orderbook Parser

Polymarket CLOB liefert Bids low-to-high und Asks high-to-low. Der Parser nutzt
deshalb:

```text
best_bid = max(bids.price)
best_ask = min(asks.price)
```

Ungültige Books werden mit `valid_orderbook = false` und `invalid_reason`
persistiert. Backtests sollen nur `valid_orderbook = true` verwenden.

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
POLYMARKET_CLOB_API_BASE_URL
POLYMARKET_ORDERBOOK_REQUESTS_PER_SECOND
```

## Entwicklung

Tests:

```bash
pytest
```

Ruff:

```bash
ruff check .
```

Projektstruktur:

```text
src/vl_polymarket_watchlist/cli.py                 CLI und Scheduler
src/vl_polymarket_watchlist/core/db/               SQLAlchemy, Alembic
src/vl_polymarket_watchlist/polymarket/            Polymarket API Client und Params
src/vl_polymarket_watchlist/markets/               Registry, Watchlist-Daten, Discovery
src/vl_polymarket_watchlist/orderbooks/            Collection, Parser, Persistence
tests/                                             Unit- und Integrationstests
```
