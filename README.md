# void-liquidity

Research tooling for Polymarket market data. The current production path is
the whale tracker in
`src/void_liquidity/adapters/polymarket/sources/track_whales`.

## Whale Tracker

The tracker performs a fresh discovery run:

1. fetch monthly PnL and volume leaderboards,
2. build candidate groups from those leaderboards,
3. fetch current positions, closed positions, and recent activity per wallet,
4. apply the configured hard filters,
5. write accepted wallets to SQLite and write a JSON report.

It only reads public Polymarket data. It does not place trades, submit orders,
cancel orders, or move funds.

Run the test suite with the project virtualenv:

```bash
.venv/bin/python -m pytest
```
