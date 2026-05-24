# void-liquidity

Research tooling for Polymarket market data. The repo is organized around a
small event-driven core so new research capabilities can be added as bindings
without coupling each step directly to the next one.

## Architecture

```text
src/void_liquidity/
  core/       event bus, domain events, binding registry, runtime
  pipeline/   provider-neutral pipeline event contracts
  adapters/   provider-specific implementations such as Polymarket signals
  bindings/    runtime connectors between pipeline events and adapters
  workflows/  runnable process composition roots
  data/       database engine, SQLAlchemy models, Alembic migrations
  logging/    JSONL logging
```

The rule is simple: pipeline stages express business intent, adapters talk to external
systems, bindings connect both sides, and `core` wires everything through events.

## Whale Tracker

The current production path is the Polymarket whale tracker. Its provider-specific
signal-discovery implementation lives at
`src/void_liquidity/adapters/polymarket/signal_discovery/whales`. It can also be
mounted as `PolymarketSignalDiscoveryBinding`.

The tracker performs a fresh discovery run:

1. fetch monthly PnL and volume leaderboards,
2. build candidate groups from those leaderboards,
3. fetch current positions, closed positions, and recent activity per wallet,
4. apply the configured hard filters,
5. write accepted wallets to SQLite and write a JSON report.

It only reads public Polymarket data. It does not place trades, submit orders,
cancel orders, or move funds.

## Current Pipeline Boundary

The current stage delivers qualified whale signals. `pipeline/signal_discovery`
owns the generic event contract, `adapters/polymarket/signal_discovery/whales`
owns the Polymarket whale implementation, and
`bindings/polymarket/signal_discovery.py` connects both sides. Downstream steps
can later subscribe to `polymarket.signal_discovery.whales.discovered`.

Run the current stage through the event-driven workflow:

```bash
.venv/bin/python -m void_liquidity.workflows.track_whales --echo-events
```

Run the test suite with the project virtualenv:

```bash
.venv/bin/python -m pytest
```
