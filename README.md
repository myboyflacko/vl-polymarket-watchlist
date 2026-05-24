# void-liquidity

Research tooling for Polymarket market data. The repo is organized around a
small event-driven core so new research capabilities can be added as plugins
without coupling each step directly to the next one.

## Architecture

```text
src/void_liquidity/
  core/       event bus, domain events, plugin registry, runtime
  features/   business capabilities such as whale tracking and later markets
  adapters/   external systems such as Polymarket HTTP APIs
  data/       database engine, SQLAlchemy models, Alembic migrations
  logging/    JSONL logging
```

The rule is simple: features express business intent, adapters talk to external
systems, and `core` wires capabilities together through events.

## Whale Tracker

The current production path is the Polymarket whale tracker. It can still be run
directly through the legacy-compatible module
`src/void_liquidity/adapters/polymarket/sources/track_whales`, and it can now
also be mounted as `PolymarketWhaleTrackingPlugin`.

The tracker performs a fresh discovery run:

1. fetch monthly PnL and volume leaderboards,
2. build candidate groups from those leaderboards,
3. fetch current positions, closed positions, and recent activity per wallet,
4. apply the configured hard filters,
5. write accepted wallets to SQLite and write a JSON report.

It only reads public Polymarket data. It does not place trades, submit orders,
cancel orders, or move funds.

## Next Feature Boundary

Wallet-to-market derivation should land under `features/markets/`. It should
consume whale snapshots or whale tracking events and produce normalized market
candidate events. Polymarket-specific fetch details stay in `adapters`.

Run the test suite with the project virtualenv:

```bash
.venv/bin/python -m pytest
```
