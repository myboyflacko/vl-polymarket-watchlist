# void-liquidity

Research tooling for Polymarket market data. The repo is organized around a
small event-driven core so new research capabilities can be added as plugins
without coupling each step directly to the next one.

## Architecture

```text
src/void_liquidity/
  core/       event bus, domain events, plugin registry, runtime
  features/   feature event contracts, currently qualified whale collection
  adapters/   external systems and collectors such as Polymarket whales
  plugins/    runtime connectors between feature events and adapters
  workflows/  runnable process composition roots
  data/       database engine, SQLAlchemy models, Alembic migrations
  logging/    JSONL logging
```

The rule is simple: features express business intent, adapters talk to external
systems, plugins connect both sides, and `core` wires everything through events.

## Whale Tracker

The current production path is the Polymarket whale tracker. It can still be run
directly through the legacy-compatible module
`src/void_liquidity/adapters/polymarket/sources/track_whales`, but the real
implementation now lives at
`src/void_liquidity/adapters/polymarket/collectors/whales`. It can also be
mounted as `PolymarketWhaleCollectorPlugin`.

The tracker performs a fresh discovery run:

1. fetch monthly PnL and volume leaderboards,
2. build candidate groups from those leaderboards,
3. fetch current positions, closed positions, and recent activity per wallet,
4. apply the configured hard filters,
5. write accepted wallets to SQLite and write a JSON report.

It only reads public Polymarket data. It does not place trades, submit orders,
cancel orders, or move funds.

## Current Feature Boundary

The current stage delivers qualified whales. `features/whales` owns the event
contract, `adapters/polymarket/collectors/whales` owns Polymarket collection,
and `plugins/polymarket/whales.py` connects that collector to the runtime.

Run the current stage through the event-driven workflow:

```bash
.venv/bin/python -m void_liquidity.workflows.track_whales --echo-events
```

Run the test suite with the project virtualenv:

```bash
.venv/bin/python -m pytest
```
