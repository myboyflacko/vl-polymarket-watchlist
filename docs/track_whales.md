# Polymarket Whale Tracking Service

This document explains `src/void_liquidity/adapters/polymarket/discovery/whales/tracker.py`.

The service builds a fresh daily Polymarket signal-whale snapshot. It does not place live trades, create orders, cancel orders, or move funds. It only reads public Polymarket Data API endpoints.

## Strategy

The service is a prefilter, not a ranking system.

It finds wallets that are large enough, currently exposed, historically profitable, recently active, and not obviously poor on risk/reward. Ranking is intentionally left for a later step.

The flow is:

1. Load the workflow profile JSON.
2. Fetch the top monthly leaderboard wallets by PnL.
3. Fetch the top monthly leaderboard wallets by volume.
4. Build three candidate pools:
   - `core`: wallets found in both top PnL and top volume.
   - `pnl_specialist`: top PnL wallets not found in top volume.
   - `volume_profitable`: top volume wallets with positive leaderboard PnL.
5. For each candidate wallet, fetch current positions.
6. Fetch closed positions inside the configured closed-position window.
7. Fetch user activity inside the configured activity window.
8. Apply hard qualification filters.
9. Persist only qualified wallets to SQLite, up to `target_wallet_count`.
10. Store reject counts in output metadata.

There is no cache-refresh mode in V2. Running the script always performs a fresh discovery.

The tracker can still be called directly, but it also supports the event-driven
runtime through `PolymarketWhaleDiscoveryBinding`. The binding consumes
`pipeline.discovery.whales.requested` and the tracker emits:

```text
pipeline.discovery.whales.started
pipeline.discovery.whales.completed
pipeline.discovery.whales.failed
polymarket.discovery.whales.discovered
```

This makes Polymarket whale discovery available without forcing
downstream steps to import provider internals directly. Future Market Discovery
handlers can subscribe to `polymarket.discovery.whales.discovered` and
load the persisted run by `run_id`.

## Workflow Profile

Whale-specific strategy settings are no longer read from `Settings.whale_tracker` or `WHALE_*` environment variables.

The default profile is:

```text
src/void_liquidity/adapters/polymarket/discovery/whales/profiles/whale_tracking_profile.json
```

The stricter quality profile is:

```text
src/void_liquidity/adapters/polymarket/discovery/whales/profiles/whale_tracking_profile_quality.json
```

The profile controls:

- candidate pool size and leaderboard request defaults
- current-position request defaults
- closed-position window and request defaults
- activity window and request defaults
- qualification thresholds
- report output path

Default balanced thresholds:

```json
{
  "candidate_pool": {
    "time_period": "MONTH",
    "top_n": 250
  },
  "filters": {
    "min_current_position_value": 10000.0,
    "min_closed_trade_count": 50,
    "min_closed_positions_pnl": 0.0,
    "min_roi": 0.0,
    "min_profit_factor": 1.5,
    "min_activity_volume": 10000.0,
    "max_largest_win_share": 0.6
  },
  "activity": {
    "trade_count_window_days": 30,
    "min_trade_count": 10,
    "last_activity_max_age_days": 7
  }
}
```

`activity.trade_count_window_days` and `activity.last_activity_max_age_days` are independent filters. The service fetches enough activity history to evaluate both.

## Endpoints

The service uses these public Polymarket Data API endpoints:

- `/v1/leaderboard`
- `/v1/positions`
- `/v1/closed-positions`
- `/activity`

All request shapes are built through Pydantic param models:

- `LeaderboardParams`
- `CurrentPositionsParams`
- `ClosedPositionsParams`
- `ActivityParams`

`ActivityParams` supports:

- `user`
- `market`
- `eventId`
- `type`
- `start`
- `end`
- `side`
- `limit`
- `offset`
- `sortBy`
- `sortDirection`

For whale tracking, activity defaults to `type=["TRADE"]`, `sortBy="TIMESTAMP"`, and `sortDirection="DESC"`.

The Polymarket activity endpoint rejects historical offsets greater than `3000`, so `ActivityParams.offset` is capped at `3000`.

When activity reaches that cap, the output keeps `activity_complete=false` and `activity_capped=true`. That means activity count and activity volume are lower bounds, not exact totals.

## Qualification

A wallet qualifies only if all hard filters pass:

```text
current_position_value >= min_current_position_value
closed_trade_count >= min_closed_trade_count
closed_positions_pnl > min_closed_positions_pnl
roi is available
roi > min_roi
profit_factor >= min_profit_factor
largest_win_share <= max_largest_win_share when available
activity_trade_count_window >= min_activity_trade_count or activity_capped=true
activity_volume_window >= min_activity_volume
last_activity_age_days <= last_activity_max_age_days
```

Incomplete current-position or closed-position fetches reject the candidate for this fresh snapshot.

Incomplete activity fetches do not reject the candidate by themselves. Activity rows are fetched newest first, so an incomplete activity scan still gives a reliable lower bound for trade count, activity volume, and `last_activity_at`. The `activity_complete` and `activity_capped` flags remain in the output as metric-quality signals. A capped activity scan is treated as sufficient for the trade-count filter because the wallet has already reached the endpoint's offset limit inside the requested window. The activity-volume filter still applies.

Closed positions without a parseable timestamp are not counted toward the closed-position window. They are recorded in `unknown_timestamp_count`.

Closed-position samples may be capped by `closed_positions.max_positions_per_wallet`. Those wallets are not rejected only because the sample is capped, but the output sets `closed_positions_truncated=true`.

Risk/reward fields are emitted for closed positions:

```text
closed_positions_cost_basis = sum(totalBought * avgPrice)
roi = closed_positions_pnl / closed_positions_cost_basis
roi_available
gross_profit
gross_loss
profit_factor = gross_profit / gross_loss
avg_win
avg_loss
largest_win
largest_win_share = largest_win / gross_profit
largest_loss
```

## Output Shape

The report output path is configured in the workflow profile. Relative paths
are resolved from the project root, not from the current shell directory.

The SQLite database location is configured centrally through
`src/void_liquidity/settings.py`, not through the whale tracking profile.
The default can be overridden with `VOID_LIQUIDITY_SQLITE_PATH`, or the full
database URL can be overridden with `VOID_LIQUIDITY_DATABASE_URL`.

The default SQLite database is:

```text
data/db/void_liquidity.sqlite3
```

Each successful run writes one row to `whale_tracker_runs` and one row per
accepted wallet to `tracked_whales`. Runs are historical snapshots; a new run
does not replace older wallet rows.

The report output path is still:

```text
data/reports/track_whales/polymarket_whales.json
```

Each run writes a report file by appending the run id to the configured file
stem:

```text
data/reports/track_whales/polymarket_whales_quality_report_20260521T104204246217Z.json
```

The same value is stored in `metadata.run_id` in the report and
`whale_tracker_runs.run_id` in SQLite.

`whale_tracker_runs` stores run-level metadata such as `run_id`,
`profile_version`, timestamps, candidate/checked/accepted counts, the workflow
profile JSON, and the generated report path.

`tracked_whales` stores one accepted wallet per run and keeps `run_id` plus
`proxy_wallet` unique.

Common query fields are denormalized into columns:

```text
candidate_pool_source
current_position_value
closed_positions_pnl
roi
profit_factor
activity_volume_window
last_activity_at
```

Each wallet row also keeps the public metric sections as JSON:

```json
{
  "metadata": {
    "proxy_wallet": "0xabc...",
    "user_name": "trader",
    "x_username": null,
    "verified_badge": false
  },
  "metrics": {
      "leaderboard": {},
      "exposure": {},
      "closed_positions": {},
      "activity": {}
    }
}
```

The service does not write `rank` or `score` in V2.

`metrics.leaderboard` includes `candidate_pool_source` and `matched_pools`, so later analysis can compare whether `core`, `pnl_specialist`, or `volume_profitable` produces better whales.

The persisted whale JSON intentionally omits low-value debug fields such as
per-wallet qualification thresholds, leaderboard identity booleans, breakeven
counts, and unknown timestamp counters. Run metadata, aggregate metric-quality
counts, and filter diagnostics are stored in the report file or run table.

The report file contains:

```json
{
  "metadata": {
    "run_id": "20260521T104204246217Z"
  },
  "profile": {},
  "candidate_funnel": {},
  "metric_quality_summary": {},
  "accepted_metrics": {},
  "threshold_margin_summary": {},
  "near_threshold_counts": {},
  "outlier_summary": {}
}
```

`accepted_metrics.overall` and `accepted_metrics.by_group` include `count`, `avg`, `median`, `p25`, `p75`, `min`, and `max` for relevant numeric whale metrics. `candidate_funnel` includes global and per-group reject summaries.

Reject details are aggregated in the report:

```json
{
  "candidate_funnel": {
    "reject_summary": {
      "current_position_value_below_min": 12
    },
    "by_group": {}
  }
}
```

Rejected wallets are not written to `tracked_whales`. `target_wallet_count` is a maximum; the service may return fewer wallets when fewer candidates pass every hard filter.

## Running

Run the event-driven workflow:

```bash
python -m void_liquidity.workflows.track_whales --echo-events
```

The workflow publishes `pipeline.discovery.whales.requested`, the Polymarket
whale-discovery binding handles that event, and the adapter implementation
persists accepted whales.

Run the provider implementation directly:

```bash
python -m void_liquidity.workflows.whale_discovery
```

The script loads the default workflow profile, performs fresh discovery, writes
the run-chain records, and persists accepted wallets to SQLite.

Run the quality profile:

```bash
python -m void_liquidity.workflows.whale_discovery
```

## Tests

Relevant tests:

```bash
.venv/bin/pytest tests/adapters/polymarket/markets/whales tests/bindings/test_polymarket_whale_discovery.py
```
