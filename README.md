# Whale Tracker

Whale Tracker sammelt Polymarket-Daten fuer eine erste Research-,
Backtesting- und Paper-Trading-Pipeline.

Der aktuelle Fokus ist bewusst pragmatisch:

- relevante Wallets finden
- offene Positionen dieser Wallets speichern
- daraus handelbare Market-Kandidaten ableiten
- Trades und Orderbooks fuer diese Kandidaten sammeln
- spaeter einfache Strategien dagegen testen

Das Projekt platziert keine Live-Trades und keine echten Orders.

## Pipeline

```text
whales -> markets -> trades -> orderbooks
```

### `whales`

Findet und bewertet Polymarket-Wallets ueber Leaderboards, Trades und offene
Positionen. Persistiert Wallet-Identitaeten, Whale-Runs und aktuelle
Whale-Metriken.

### `markets`

Laedt die offenen Positionen der ausgewaehlten Whales und speichert sie als
wallet-level Positionen.

Wichtig: `polymarket_markets` ist die Market-Identity-Tabelle. Eine Zeile steht
fuer einen Token, also eine handelbare Seite eines Conditions-Markets.

Die aktuelle Market-Auswahl ist eine Read-View auf den gespeicherten Positionen:

```text
dominant_side_5_whales_80_percent_latest_run
```

Sie nutzt den letzten completed Market-Run und waehlt pro `condition_id` die
dominante Token-Seite, wenn:

- mindestens 5 unique Wallets auf der dominanten Seite liegen
- die dominante Seite mindestens 80% aller unique Wallets der Condition stellt

Die Gegenseite disqualifiziert den Market nicht automatisch. Entscheidend ist
die Ratio.

### `trades`

Sammelt Trades fuer die ausgewaehlten Markets. Quellen sind die Wallets aus der
Market-Read-View, gruppiert nach `wallet + condition_id`.

Trades werden global dedupliziert und pro Run verlinkt. Ein einfacher Time-Sync
verhindert, dass bekannte Trades am zuletzt gesehenen Timestamp erneut
gespeichert werden. Der erste Lauf kann deshalb gross sein; spaetere Laeufe
sollten deutlich weniger neue Zeilen speichern, muessen aber weiterhin die
relevanten Quellen abfragen.

### `orderbooks`

Sammelt Orderbook-Snapshots fuer die ausgewaehlten Markets. Orderbook-Metriken
referenzieren direkt `polymarket_markets.market_id`, nicht mehr eine alte
Tracked-Market-Tabelle.

## CLI

Lokale Installation:

```bash
python -m pip install -e .
```

Datenbank migrieren:

```bash
whale-tracker init-db
```

Einzelne Services ausfuehren:

```bash
whale-tracker run whales
whale-tracker run markets
whale-tracker run trades
whale-tracker run orderbooks
whale-tracker run all
```

Nuetzliche Optionen:

```bash
whale-tracker run markets --whales-run-id <run_id>
whale-tracker run trades --market-run-id <run_id>
whale-tracker run orderbooks --market-run-id <run_id> --orderbook-depth 5
```

`run all` fuehrt nacheinander `whales`, `markets`, `trades` und `orderbooks` aus
und reicht die erzeugten Run-IDs intern weiter.

## Scheduler

Scheduler starten:

```bash
whale-tracker schedule
```

Default-Intervalle:

| Service | Intervall |
| --- | ---: |
| whales | 3600s |
| markets | 900s |
| trades | 1200s |
| orderbooks | 300s |

Anpassung:

```bash
whale-tracker schedule \
  --whales-interval 3600 \
  --markets-interval 900 \
  --trades-interval 1200 \
  --orderbooks-interval 300 \
  --orderbook-depth 5
```

Blockierlogik:

- `markets` wartet, wenn `whales` laeuft
- `trades` wartet, wenn `markets` laeuft
- `orderbooks` wartet, wenn `markets` laeuft
- `trades` wird uebersprungen, wenn ein Trade-Run noch laeuft
- `orderbooks` wird uebersprungen, wenn ein Orderbook-Run noch laeuft
- `trades` und `orderbooks` duerfen parallel laufen

## HTTP API

API starten:

```bash
whale-tracker api
```

Endpoints:

- `GET /whale-observations`
- `GET /markets`
- `GET /orderbooks`

Alle Endpoints nutzen standardmaessig den letzten passenden Run. Optional kann
ein `run_id` gesetzt werden:

```text
/markets?run_id=20260611T120000000000Z-markets
/orderbooks?run_id=20260611T120500000000Z-orderbooks
```

## Docker

Image bauen:

```bash
docker compose build
```

Datenbank starten:

```bash
docker compose up -d postgres
```

Migrationen ausfuehren:

```bash
docker compose run --rm cli init-db
```

Scheduler starten:

```bash
docker compose up -d scheduler
```

API starten:

```bash
docker compose up -d api
```

Logs:

```bash
docker compose logs -f scheduler
docker compose logs -f api
```

## Konfiguration

Settings kommen aus Environment-Variablen oder `.env`.

Wichtige Variablen:

```text
WHALE_TRACKER_POSTGRES_DB
WHALE_TRACKER_POSTGRES_USER
WHALE_TRACKER_POSTGRES_PASSWORD
WHALE_TRACKER_POSTGRES_HOST
WHALE_TRACKER_POSTGRES_PORT
WHALE_TRACKER_LOG_LEVEL

POLYMARKET_DATA_API_BASE_URL
POLYMARKET_DATA_API_TIMEOUT_SECONDS
POLYMARKET_DATA_API_MAX_CONCURRENT_REQUESTS
POLYMARKET_DATA_API_REQUEST_DELAY_SECONDS
POLYMARKET_DATA_API_RATE_LIMIT_RETRY_ATTEMPTS
POLYMARKET_DATA_API_RATE_LIMIT_BACKOFF_SECONDS
POLYMARKET_DATA_API_REQUESTS_PER_SECOND
POLYMARKET_TRADES_REQUESTS_PER_SECOND
POLYMARKET_POSITIONS_REQUESTS_PER_SECOND
POLYMARKET_LEADERBOARD_REQUESTS_PER_SECOND
```

Interne PostgreSQL-URL:

```text
postgresql+psycopg://USER:PASSWORD@HOST:PORT/DB
```

## Datenmodell

Die wichtigsten Tabellen:

| Tabelle | Zweck |
| --- | --- |
| `polymarket_wallets` | Wallet-Identity |
| `polymarket_whale_runs` | Whale-Run-Metadaten |
| `polymarket_whale_observations` | Whale-Metriken pro Run |
| `polymarket_markets` | Market-/Token-Identity |
| `polymarket_market_runs` | Market-Run-Metadaten |
| `polymarket_market_positions` | Offene Wallet-Positionen pro Market-Run |
| `polymarket_trade_runs` | Trade-Run-Metadaten |
| `polymarket_trades` | Deduplizierte Trade-Facts |
| `polymarket_trade_run_items` | Zuordnung Trade-Facts zu Trade-Runs |
| `polymarket_orderbook_runs` | Orderbook-Run-Metadaten |
| `polymarket_orderbook_metrics` | Orderbook-Snapshots und Metriken |

## Backtesting-Stand

Der aktuelle Stand reicht fuer ein erstes MVP-Backtesting:

- ausgewaehlte Whales
- offene Positionen je Run
- ausgewaehlte Markets ueber Read-View
- historische Trades fuer diese Markets und Wallets
- Orderbook-Snapshots fuer die ausgewaehlten Markets

Noch nicht fertig fuer sauberes Backtesting:

- Market-Resolution und Outcome-Daten
- harte Timestamp-Cutoffs gegen Lookahead-Bias
- Slippage-, Fee- und Fill-Modell
- Strategy Runner mit Entry-, Exit- und Sizing-Regeln
- Paper-Trading-Ausfuehrung ohne echte Orders

Die sinnvolle Reihenfolge ist:

```text
1. Daten stabil sammeln
2. einfache Backtesting-Dataset-View bauen
3. erste Strategie offline testen
4. Paper Trading ohne echte Orders
5. erst danach Live-Trading separat planen
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

Integrationstests gegen PostgreSQL brauchen eine Test-Datenbank. Der Datenbankname
muss `test` enthalten:

```bash
WHALE_TRACKER_TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/whale_tracker_test pytest
```

## Projektstruktur

```text
src/whale_tracker/cli.py                  CLI, Scheduler, API-Start
src/whale_tracker/api/                    FastAPI Read-Endpoints
src/whale_tracker/core/db/                SQLAlchemy, Alembic
src/whale_tracker/providers/polymarket/   Polymarket API Client und Params
src/whale_tracker/tracker/whales/         Whale Discovery und Persistence
src/whale_tracker/tracker/markets/        Position Collection und Market Read-View
src/whale_tracker/tracker/trades/         Trade Collection und Deduplication
src/whale_tracker/tracker/orderbooks/     Orderbook Collection
tests/                                    Unit- und Integrationstests
```
