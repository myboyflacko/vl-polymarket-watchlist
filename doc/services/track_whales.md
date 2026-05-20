# Polymarket Whale Tracking Service

This document explains `src/void_liquidity/adapters/polymarket/services/track_whales.py`.

The service discovers Polymarket wallets from the leaderboard, validates their recent trading quality with closed positions, ranks them by leaderboard PnL, and writes the result to JSON when run as a script.

No live trades, orders, or fund movements happen in this service. It only reads public Polymarket data.

## High-Level Flow

`track_whales()` does the following:

1. Create one `HTTPClient`.
2. Fetch leaderboard pages from Polymarket with `timePeriod=MONTH` and `orderBy=PNL` by default.
3. Extract each `proxyWallet`.
4. Skip wallets that were already seen.
5. Process wallets in small async batches.
6. Fetch each wallet's closed positions by `TIMESTAMP DESC`.
7. Keep only closed positions inside the configured lookback window.
8. Calculate quality metrics from those closed positions.
9. Keep wallets with:
   - at least 50 closed positions in the lookback window
   - win rate greater than or equal to 70%
10. Sort qualified wallets by leaderboard PnL.
11. Assign final ranks.
12. Return a dict keyed by `proxy_wallet`.

When the file is run directly, it runs the daily refresh flow and writes:

```text
data/polymarket_whales.json
```

## Discovery Vs Refresh

There are two workflows:

- `track_whales()` performs a fresh discovery from the leaderboard.
- `refresh_whales()` loads the existing JSON cache, revalidates it, removes stale wallets, then fills missing slots from the leaderboard.

`refresh_whales()` is the normal daily operational mode.

If no JSON cache exists, `refresh_whales()` behaves like a first run: it starts with an empty cache and fills from the leaderboard.

## Daily Refresh Flow

`refresh_whales()` does the following:

1. Load existing whales from `WHALE_OUTPUT_PATH`.
2. Revalidate every cached wallet:
   - fetch its current leaderboard entry
   - fetch current closed positions inside the lookback window
   - recalculate metrics
3. Keep cached wallets that still qualify.
4. Remove cached wallets that no longer qualify.
5. Keep cached wallets if validation was incomplete because of rate-limit exhaustion.
6. Scan leaderboard pages for replacement candidates.
7. Skip candidates already checked or already in the refreshed cache.
8. Add qualified new wallets until `WHALE_TARGET_COUNT` is reached.
9. Sort final wallets by leaderboard PnL.
10. Reassign ranks.
11. Write the refreshed JSON cache.

This avoids dropping a wallet just because the API was temporarily rate-limited. A wallet is removed only when the service can complete validation and the wallet fails the criteria, or when no current leaderboard entry can be fetched for it.

## Role Split

The service intentionally separates ranking from validation:

- Leaderboard is the PnL and ranking source.
- Closed Positions are only the quality check.

That avoids having two competing PnL definitions. Polymarket leaderboard PnL decides the final order; closed positions only answer whether the wallet has enough recent closed trades and a strong enough win rate.

## Return Shape

`track_whales()` returns:

```python
dict[str, dict[str, Any]]
```

The outer key is the wallet address. The in-memory result contains the fetched `closed_positions` because those positions are needed for validation and metric calculation.

Example entry:

```python
{
    "0xabc...": {
        "proxy_wallet": "0xabc...",
        "user_name": "trader",
        "leaderboard": {...},
        "closed_positions": [...],
        "metrics": {
            "closed_trade_count": 63,
            "wins": 47,
            "losses": 16,
            "win_rate": 0.746031746,
            "closed_positions_pnl": 123.45,
            "avg_pnl_per_trade": 1.9595238095,
        },
        "rank": 1,
    }
}
```

`closed_positions_pnl` and `avg_pnl_per_trade` are diagnostic fields. They are not used for final ranking or filtering.

The JSON output is intentionally slimmer than the in-memory result and does not include `closed_positions`.

## Qualification And Ranking

The service qualifies wallets with:

```python
closed_trade_count >= MIN_TRADE_COUNT
win_rate >= MIN_WIN_RATE
```

The final ranking uses:

```python
leaderboard["pnl"]
```

descending.

## Closed Positions Sampling

Closed positions are requested with:

```python
sortBy="TIMESTAMP"
sortDirection="DESC"
```

The service evaluates newest closed positions first and stops once it reaches positions older than the lookback cutoff.

The timestamp parser accepts these fields, in this order:

- `timestamp`
- `createdAt`
- `updatedAt`
- `closedAt`

Values may be ISO timestamps, Unix seconds, or Unix milliseconds.

The service stops fetching positions for a wallet when one of these happens:

- it reached a position older than `LOOKBACK_DAYS`
- it collected `MAX_CLOSED_POSITIONS_PER_WALLET`
- Polymarket returns an empty or invalid page
- Polymarket returns a page smaller than the requested `ClosedPositionsParams.limit`
- the `ClosedPositionsParams.offset` maximum is reached
- rate limit retries are exhausted

If rate limit retries are exhausted, the wallet is marked incomplete and skipped. It is not rejected as if it had zero trades.

## Settings

Whale tracker defaults live in `WhaleTrackerSettings` in `src/void_liquidity/settings.py`.

The settings object holds both strategy/runtime values and the default API request shape used by the whale tracker. API request values are still validated by the existing Pydantic param models in `src/void_liquidity/adapters/polymarket/params/` when `track_whales.py` builds `LeaderboardParams` and `ClosedPositionsParams`.

The values below are loaded from `src/void_liquidity/settings.py` and can be overridden through environment variables. `track_whales.py` reads them at import time.

| Env var | Default | Meaning |
| --- | ---: | --- |
| `WHALE_TARGET_COUNT` | `50` | Stop once this many qualified wallets are found. |
| `WHALE_LOOKBACK_DAYS` | `30` | Only closed positions newer than this many days are evaluated. |
| `WHALE_MIN_TRADE_COUNT` | `50` | Minimum closed positions required inside the lookback window. |
| `WHALE_MIN_WIN_RATE` | `0.70` | Minimum win rate required. Uses `realizedPnl > 0` as a win. |
| `WHALE_MAX_CLOSED_POSITIONS_PER_WALLET` | `500` | Safety cap for positions kept per wallet inside the lookback scan. |
| `WHALE_BATCH_SIZE` | `2` | Number of wallet scans started together with `asyncio.gather`. |
| `WHALE_OUTPUT_PATH` | `data/polymarket_whales.json` | JSON output path used by `__main__`. |
| `WHALE_LEADERBOARD_TIME_PERIOD` | `MONTH` | Default leaderboard period. Validated by `LeaderboardParams`. |
| `WHALE_LEADERBOARD_ORDER_BY` | `PNL` | Default leaderboard sort. Validated by `LeaderboardParams`. |
| `WHALE_LEADERBOARD_LIMIT` | `50` | Default leaderboard page size. Validated by `LeaderboardParams`. |
| `WHALE_CLOSED_POSITIONS_LIMIT` | `50` | Default closed-position page size. Validated by `ClosedPositionsParams`. |
| `WHALE_CLOSED_POSITIONS_SORT_BY` | `TIMESTAMP` | Default closed-position sort field. Validated by `ClosedPositionsParams`. |
| `WHALE_CLOSED_POSITIONS_SORT_DIRECTION` | `DESC` | Default closed-position sort direction. Validated by `ClosedPositionsParams`. |
| `MAX_CONCURRENT_PROFILE_REQUESTS` | `1` | Hard cap for simultaneous closed-position API calls. |
| `POLYMARKET_REQUEST_DELAY_SECONDS` | `1.0` | Delay before each closed-position API call. |
| `POLYMARKET_RATE_LIMIT_RETRY_ATTEMPTS` | `5` | Number of retries after rate-limit errors. |
| `POLYMARKET_RATE_LIMIT_BACKOFF_SECONDS` | `60.0` | Base backoff duration. Wait time is multiplied by attempt number. |

Example `.env` values:

```env
WHALE_LOOKBACK_DAYS=30
WHALE_MIN_TRADE_COUNT=50
WHALE_MIN_WIN_RATE=0.70
WHALE_OUTPUT_PATH=data/polymarket_whales.json
WHALE_LEADERBOARD_TIME_PERIOD=MONTH
WHALE_LEADERBOARD_ORDER_BY=PNL
WHALE_LEADERBOARD_LIMIT=50
WHALE_CLOSED_POSITIONS_LIMIT=50
WHALE_CLOSED_POSITIONS_SORT_BY=TIMESTAMP
WHALE_CLOSED_POSITIONS_SORT_DIRECTION=DESC
MAX_CONCURRENT_PROFILE_REQUESTS=1
POLYMARKET_REQUEST_DELAY_SECONDS=1.0
POLYMARKET_RATE_LIMIT_RETRY_ATTEMPTS=5
POLYMARKET_RATE_LIMIT_BACKOFF_SECONDS=60.0
```

Do not raise concurrency aggressively after Cloudflare `1015` or HTTP `429`. The API may temporarily block the client IP.

## Request Params

The service builds API requests through the existing Pydantic param models.

The default leaderboard params are derived from `WhaleTrackerSettings`:

```python
DEFAULT_LEADERBOARD_PARAMS = LeaderboardParams(
    timePeriod=whale_tracker_settings.leaderboard_time_period,
    orderBy=whale_tracker_settings.leaderboard_order_by,
    limit=whale_tracker_settings.leaderboard_limit,
)
```

The default closed-position params are also derived from `WhaleTrackerSettings`:

```python
DEFAULT_CLOSED_POSITIONS_PARAMS = ClosedPositionsParams(
    user="0x0000000000000000000000000000000000000000",
    limit=whale_tracker_settings.closed_positions_limit,
    sortBy=whale_tracker_settings.closed_positions_sort_by,
    sortDirection=whale_tracker_settings.closed_positions_sort_direction,
)
```

`ClosedPositionsParams` needs a wallet address, so the default object uses a placeholder wallet only to validate shared request fields. During scanning, the service replaces `user` and `offset` for each wallet:

```python
DEFAULT_CLOSED_POSITIONS_PARAMS.model_copy(
    update={"user": proxy_wallet, "offset": offset}
)
```

You can override the API request shape by passing param objects directly:

```python
await track_whales(
    leaderboard_params=LeaderboardParams(
        timePeriod="WEEK",
        orderBy="PNL",
        limit=25,
    ),
    closed_positions_params=ClosedPositionsParams(
        user="0x0000000000000000000000000000000000000000",
        limit=25,
        sortBy="TIMESTAMP",
        sortDirection="DESC",
    ),
)
```

The wallet and offset fields in `closed_positions_params` are overwritten during scanning. That means the object is useful for shared filters such as `limit`, `sortBy`, `sortDirection`, `market`, or `eventId`, while the service still controls the current wallet and page.

For cached-wallet revalidation, the service derives a wallet-specific leaderboard request from the base leaderboard params:

```python
base_params.model_copy(update={"limit": 1, "offset": 0, "user": proxy_wallet})
```

This keeps the defaults centralized in settings while still letting the param models reject invalid API values such as unsupported `timePeriod`, `sortBy`, or page sizes above the API model limits.

## Async Behavior

There are two separate controls:

`WHALE_BATCH_SIZE` controls how many wallet scans are started together.

`MAX_CONCURRENT_PROFILE_REQUESTS` controls how many actual `/v1/closed-positions` requests are allowed at the same time.

Example:

```text
WHALE_BATCH_SIZE=2
MAX_CONCURRENT_PROFILE_REQUESTS=1
```

Two wallet scan tasks are created, but only one actual profile request runs at once.

Example:

```text
WHALE_BATCH_SIZE=2
MAX_CONCURRENT_PROFILE_REQUESTS=2
```

Two wallet scan tasks are created, and up to two actual profile requests may run at the same time.

The request delay still applies before every closed-position call.

## Rate Limit Handling

`get_closed_positions()` detects rate limits by checking exception text for:

- `429`
- `Too Many Requests`
- `Error 1015`
- `you are being rate limited`

On rate limit:

1. Print a retry message.
2. Sleep for `POLYMARKET_RATE_LIMIT_BACKOFF_SECONDS * attempt`.
3. Retry until attempts are exhausted.
4. Raise `PolymarketRateLimitError`.

`track_whales()` catches `PolymarketRateLimitError` inside `_fetch_all_closed_positions()` and returns:

```python
(partial_positions, False)
```

The `False` marks the wallet as incomplete. Incomplete wallets are skipped.

## JSON Output

`write_whales_to_json(whales, path)` writes a cache/API-friendly payload:

```json
{
  "metadata": {
    "generated_at": "2026-05-19T12:00:00+00:00",
    "lookback_days": 30,
    "target_whale_count": 50,
    "min_trade_count": 50,
    "min_win_rate": 0.7,
    "leaderboard_time_period": "MONTH",
    "leaderboard_order_by": "PNL",
    "wallet_count": 50,
    "refreshed_at": "2026-05-19T12:01:00+00:00",
    "mode": "refresh",
    "removed_wallet_count": 4,
    "added_wallet_count": 4,
    "kept_wallet_count": 46,
    "incomplete_wallet_count": 0,
    "checked_wallet_count": 84
  },
  "whales": {
    "0xabc...": {
      "proxy_wallet": "0xabc...",
      "user_name": "trader",
      "rank": 1,
      "leaderboard_entry": {},
      "metrics": {}
    }
  }
}
```

This shape is easier to reuse later for Redis, API responses, update jobs, and re-ranking than a CSV file.

`closed_positions` are deliberately excluded from the JSON cache because they make the file large and are only needed during validation. On the next refresh, the service fetches current closed positions again.

Refresh metadata fields are written only by `refresh_whales()`.

## Progress Output

The service prints progress with prefixes:

| Prefix | Meaning |
| --- | --- |
| `[track_whales]` | Start and final script summary. |
| `[leaderboard]` | Leaderboard page calls and page stats. |
| `[wallet_batch]` | Wallet batch execution. |
| `[closed_positions]` | Closed-position page calls and stop reasons. |
| `[rate_limit]` | Rate-limit attempts and backoff waits. |
| `[qualified]` | Wallet passed filters. |
| `[rejected]` | Wallet failed filters. |
| `[skipped]` | Wallet was incomplete due to rate limit. |
| `[done]` | Final ranked wallets and final counts. |
| `[json]` | JSON write result. |
| `[refresh_existing]` | Cached wallet is being revalidated. |
| `[refresh_kept]` | Cached wallet remains in the cache. |
| `[refresh_removed]` | Cached wallet was removed. |
| `[refresh_added]` | New wallet was added from the leaderboard. |
| `[refresh_done]` | Daily refresh summary. |

## Current Tradeoffs

Good:

- Leaderboard PnL stays the single ranking source.
- Closed positions validate recent activity and win rate without redefining PnL.
- JSON output is ready for cache/API-style reuse.
- Rate-limit handling avoids treating blocked requests as empty wallets.

Limitations:

- Win rate depends on the closed positions returned and timestamp parsing.
- Wallets with fewer than 50 closed positions in the lookback window are rejected even if their leaderboard PnL is high.
- Diagnostic closed-position PnL can differ from leaderboard PnL.

## Safe Tuning Order

Start conservative:

```env
MAX_CONCURRENT_PROFILE_REQUESTS=1
POLYMARKET_REQUEST_DELAY_SECONDS=1.0
```

If stable, try:

```env
MAX_CONCURRENT_PROFILE_REQUESTS=2
POLYMARKET_REQUEST_DELAY_SECONDS=0.75
```

If Cloudflare `1015` or HTTP `429` appears again, reduce concurrency or increase delay/backoff.
