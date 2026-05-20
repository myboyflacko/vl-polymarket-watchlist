# Polymarket Whale Tracking Service

This document explains `src/void_liquidity/adapters/polymarket/services/track_whales.py`.

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
9. Write only qualified wallets to JSON, up to `target_wallet_count`.
10. Store reject counts in output metadata.

There is no cache-refresh mode in V2. Running the script always performs a fresh discovery.

## Workflow Profile

Whale-specific strategy settings are no longer read from `Settings.whale_tracker` or `WHALE_*` environment variables.

The default profile is:

```text
src/void_liquidity/adapters/polymarket/services/config/whale_tracking_profile.json
```

The profile controls:

- candidate pool size and leaderboard request defaults
- current-position request defaults
- closed-position window and request defaults
- activity window and request defaults
- qualification thresholds
- output path

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
    "min_win_rate": 0.7,
    "min_closed_positions_pnl": 0.0
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
win_rate >= min_win_rate
closed_positions_pnl > min_closed_positions_pnl
activity_trade_count_window >= min_activity_trade_count
last_activity_age_days <= last_activity_max_age_days
```

Incomplete current-position or closed-position fetches reject the candidate for this fresh snapshot.

Incomplete activity fetches do not reject the candidate by themselves. Activity rows are fetched newest first, so an incomplete activity scan still gives a reliable lower bound for trade count and a reliable `last_activity_at`. The `activity_complete` flag remains in the output as a metric-quality signal.

Closed positions without a parseable timestamp are not counted toward the closed-position window. They are recorded in `unknown_timestamp_count`.

Closed-position samples may be capped by `closed_positions.max_positions_per_wallet`. Those wallets are not rejected only because the sample is capped, but the output sets `closed_positions_truncated=true`.

Risk/reward fields are also emitted for closed positions:

```text
closed_positions_volume
roi = closed_positions_pnl / closed_positions_volume
gross_profit
gross_loss
profit_factor = gross_profit / gross_loss
avg_win
avg_loss
largest_loss
```

## Output Shape

The output path is configured in the workflow profile. Relative output paths are resolved from the project root, not from the current shell directory. The default is:

```text
src/void_liquidity/adapters/polymarket/services/data/polymarket_whales.json
```

The outer `whales` object is keyed by `proxy_wallet`.

Each whale has:

```json
{
  "metadata": {
    "proxy_wallet": "0xabc...",
    "user_name": "trader",
    "x_username": null,
    "profile_image": "",
    "verified_badge": false
  },
  "metrics": {
    "leaderboard": {},
    "exposure": {},
    "closed_positions": {},
    "activity": {},
    "qualification": {}
  }
}
```

The service does not write `rank` or `score` in V2.

`metrics.leaderboard` includes `candidate_pool_source` and `matched_pools`, so later analysis can compare whether `core`, `pnl_specialist`, or `volume_profitable` produces better whales.

Reject details are aggregated in:

```json
{
  "metadata": {
    "reject_summary": {
      "current_position_value_below_min": 12
    }
  }
}
```

Rejected wallets are not written to the main output. `target_wallet_count` is a maximum; the service may return fewer wallets when fewer candidates pass every hard filter.

## Running

Run the service module:

```bash
python -m void_liquidity.adapters.polymarket.services.track_whales
```

The script loads the default workflow profile, performs fresh discovery, and writes the configured JSON output.

## Tests

Relevant tests:

```bash
.venv/bin/pytest tests/test_polymarket_activity_params.py tests/test_track_whales_v2.py
```
