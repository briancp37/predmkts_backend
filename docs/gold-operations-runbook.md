# Gold Layer Operations Runbook

## Overview

The Gold layer computes aggregations and analytics from Silver Iceberg tables, storing results as day-partitioned Parquet in S3 and serving them via ClickHouse for low-latency queries. Key computations include position accounting, wallet PnL, market marks, and on-demand wallet snapshots.

**Database:** `prediction_gold` in ClickHouse.

**S3 path convention:** `gold/{table_name}/day={YYYY-MM-DD}/part-000.parquet`

## Daily Operations

### Running the Daily Pipeline

The `daily-run` command executes all Gold processing steps in sequence:

```bash
# Process yesterday (default)
prediction-data gold daily-run

# Process a specific date
prediction-data gold daily-run --dt 2024-06-15

# Preview without writing
prediction-data gold daily-run --dry-run

# Halt on first step failure (default: continue to next step)
prediction-data gold daily-run --stop-on-error
```

**Execution order:**
1. `load-dims` — Load dimension tables (platforms, markets, outcomes, wallets, events, categories)
2. `process-trades` — Process Silver trades through position accounting engine → ledger + position state
3. `compute-marks` — Compute market marks (VWAP, last price, volume) from Silver trades
4. `compute-wallet-metrics` — Compute wallet_pnl_daily (all wallets) + wallet_mtm_daily + wallet_position_snapshot_daily (watchlist only)

By default, failures are logged and the pipeline continues to the next step (fail-forward). Use `--stop-on-error` to halt on first failure.

### Scheduled Processing (EventBridge)

| Schedule | Time (UTC) | Command | Description |
|----------|------------|---------|-------------|
| daily-run | 00:00 | `gold daily-run` | Full daily processing |
| ch-load | 00:30 | `gold ch-load --all --lookback-days 90` | Load S3 → ClickHouse |
| freshness | 01:00 | `gold freshness` | Verify SLAs |

Infrastructure template: `infrastructure/eventbridge-gold-schedules.yaml`

### Loading Data into ClickHouse

After daily processing writes Parquet to S3, load into ClickHouse:

```bash
# Load a specific table
prediction-data gold ch-load --table market_mark_daily --lookback-days 90

# Load all Gold tables
prediction-data gold ch-load --all --lookback-days 90

# Preview
prediction-data gold ch-load --table wallet_pnl_daily --dry-run
```

**Loadable tables:** `market_mark_daily`, `wallet_pnl_daily`, `wallet_mtm_daily`, `wallet_position_snapshot_daily`

The `--lookback-days` parameter limits how many days of data are loaded (default: 90). ClickHouse TTL expressions automatically expire older data.

## Position Accounting

### Overview

The position accounting engine processes Silver trades into a position ledger with per-fill PnL and maintains cumulative position state.

```bash
# Process a single day
prediction-data gold process-trades --dt 2024-06-15

# Process a date range (sequential — order matters for cumulative state)
prediction-data gold process-trades --start-date 2024-06-01 --end-date 2024-06-30

# Force reprocess already-processed dates
prediction-data gold process-trades --dt 2024-06-15 --force-reprocess
```

### Accounting Methodology

**Average-cost basis:**
- Buy increases position: `new_avg_cost = (old_qty * old_avg_cost + qty_delta * price) / new_qty`
- Sell reduces position: `realized_pnl = closed_qty * (price - avg_cost) - fees`, avg_cost unchanged

**Position flips:**
When a sell exceeds the current position (e.g., sell 150 when holding 100 long):
1. Close the existing 100-unit position (realize PnL)
2. Open a new 50-unit short position at the fill price

**Ledger records:**
Each fill records `qty_before`, `qty_after`, `avg_cost_before`, `avg_cost_after`, `realized_pnl_this_fill_usd` for full audit trail.

### ClickHouse Tables

**wallet_position_ledger** — Append-only per-fill records:
```sql
ts                          DateTime64(6, 'UTC')
wallet                      String
platform                    String
market_id                   String
outcome_id                  String
side                        String          -- 'buy' or 'sell'
qty_delta                   Float64
price                       Float64
fees_usd                    Float64
qty_before                  Float64
qty_after                   Float64
avg_cost_before             Float64
avg_cost_after              Float64
realized_pnl_this_fill_usd  Float64
```

**wallet_position_state** — Current position per (wallet, platform, market_id, outcome_id):
```sql
wallet          String
platform        String
market_id       String
outcome_id      String
qty             Float64         -- positive = long, negative = short
avg_cost        Float64
cost_basis_usd  Float64
last_fill_ts    DateTime64(6, 'UTC')
first_open_ts   DateTime64(6, 'UTC')
```

Uses `ReplacingMergeTree(last_fill_ts)` — query with `FINAL` to get latest state.

## Market Marks

```bash
# Compute marks for a single day
prediction-data gold compute-marks --dt 2024-06-15 --platform polymarket

# Compute for a date range
prediction-data gold compute-marks --start-date 2024-06-01 --end-date 2024-06-30
```

**Computed metrics:**
- `mark_price` — VWAP for the day
- `last_trade_price` — Price of the most recent trade
- `volume_usd_24h` — Total USD volume
- `trades_count_24h` — Number of trades
- `active_wallets_24h` — Distinct maker + taker addresses
- `liquidity_metric` — Derived liquidity indicator

**ClickHouse schema (market_mark_daily):**
```sql
platform           String
market_id          String
outcome_id         String
day_utc            Date
mark_price         Float64
last_trade_price   Float64
volume_usd_24h     Float64
trades_count_24h   UInt64
active_wallets_24h UInt64
liquidity_metric   Float64
version            UInt64
```

## Wallet Metrics

### wallet_pnl_daily (All Wallets)

Aggregates realized PnL from the position ledger:

```bash
prediction-data gold compute-pnl --dt 2024-06-15
prediction-data gold compute-pnl --start-date 2024-06-01 --end-date 2024-06-30
```

**Schema:**
```sql
day_utc          Date
wallet           String
realized_pnl_usd Float64
fees_usd         Float64
volume_usd       Float64
trades_count     UInt64
wins             UInt64
losses           UInt64
version          UInt64
```

### wallet_mtm_daily and wallet_position_snapshot_daily (Watchlist Only)

These tables are computed only for wallets on the Gold watchlist:

```bash
# Compute MTM
prediction-data gold compute-mtm --dt 2024-06-15

# Compute position snapshots
prediction-data gold compute-position-snapshot --dt 2024-06-15

# Compute all wallet metrics at once
prediction-data gold compute-wallet-metrics --dt 2024-06-15
```

### Watchlist Management

```bash
# Add a wallet
prediction-data gold watchlist add 0x742d35Cc6634C0532925a3b844Bc9e7595f8

# Remove (deactivate) a wallet
prediction-data gold watchlist remove 0x742d35Cc6634C0532925a3b844Bc9e7595f8

# List active wallets
prediction-data gold watchlist list

# Include inactive wallets
prediction-data gold watchlist list --all
```

## Backfills and Rebuilds

### Rebuilding Gold Tables

```bash
# Rebuild market marks (independent per day — can skip existing)
prediction-data gold rebuild --table market_mark_daily \
    --start-date 2024-06-01 --end-date 2024-06-30

# Force overwrite existing partitions
prediction-data gold rebuild --table market_mark_daily \
    --start-date 2024-06-01 --end-date 2024-06-30 --force

# Rebuild cumulative tables (always processes sequentially)
prediction-data gold rebuild --table wallet_pnl_daily \
    --start-date 2024-06-01 --end-date 2024-06-30
```

**Table types:**
- **Independent:** `market_mark_daily` — each day can be rebuilt independently
- **Cumulative:** `wallet_pnl_daily`, `wallet_mtm_daily`, `wallet_position_snapshot_daily` — depend on position state, always processed earliest-first

### On-Demand Wallet Snapshots

Reconstruct position snapshots for a specific wallet:

```bash
prediction-data gold compute-snapshot \
    --wallet 0x742d35Cc6634C0532925a3b844Bc9e7595f8 \
    --start-date 2024-01-01 \
    --end-date 2024-06-30

# Skip ClickHouse loading (S3 only)
prediction-data gold compute-snapshot \
    --wallet 0x742d35... \
    --start-date 2024-01-01 \
    --end-date 2024-06-30 \
    --skip-ch

# Adjust chunk size (default 30 days per batch)
prediction-data gold compute-snapshot \
    --wallet 0x742d35... \
    --start-date 2024-01-01 \
    --end-date 2024-06-30 \
    --chunk-days 60
```

## Freshness Monitoring

### Checking Freshness

```bash
prediction-data gold freshness
```

Output example:
```
Dataset                                  State    Lag (s)    SLA (s)    Last Success
----------------------------------------------------------------------------------------------------
market_mark_daily                        fresh    120        300        2024-06-15 00:15:32
wallet_pnl_daily                         fresh    180        600        2024-06-15 00:18:45
wallet_mtm_daily                         stale    1200       900        2024-06-15 00:10:00
wallet_position_snapshot_daily           broken   —          900        —
```

### SLA Thresholds

| Dataset | SLA (seconds) | SLA (human) |
|---------|--------------|-------------|
| `market_mark_daily` | 300 | 5 min |
| `wallet_pnl_daily` | 600 | 10 min |
| `wallet_mtm_daily` | 900 | 15 min |
| `wallet_position_snapshot_daily` | 900 | 15 min |

### Freshness States

| State | Definition |
|-------|-----------|
| `fresh` | `actual_lag <= SLA` |
| `stale` | `SLA < actual_lag <= 2×SLA` |
| `broken` | `actual_lag > 2×SLA` OR last run failed |

## Dimension Tables

```bash
# Load all dimension tables
prediction-data gold load-dims

# Load a specific dimension
prediction-data gold load-dims --table dim_market

# Preview
prediction-data gold load-dims --dry-run
```

**Available dimensions:**
- `dim_platform` — Platform metadata (polymarket, kalshi)
- `dim_market` — Market metadata from Silver
- `dim_outcome` — Outcome metadata
- `dim_wallet` — Wallet metadata (derived from trades)
- `dim_event` — Event metadata
- `dim_category` — Category metadata

## Troubleshooting

### Common Issues

**"ClickHouse connection refused"**
- Verify ClickHouse is running: `docker compose ps`
- Check `CLICKHOUSE_HOST` and `CLICKHOUSE_PORT` environment variables
- Local development: `docker compose up -d clickhouse`

**"GOLD_BUCKET not configured"**
- Set the `GOLD_BUCKET` environment variable to your S3 bucket name

**"No Silver trades found for date"**
- Verify Silver data exists for the date: check Glue Catalog or query Iceberg directly
- Ensure Silver processing has completed for that date

**Position state mismatch after backfill**
- Position accounting is cumulative — dates must be processed in order
- Use `--force-reprocess` from the earliest affected date to rebuild state

**Stale/broken freshness status**
- Check `pipeline_runs` table for failed runs: `SELECT * FROM pipeline_runs WHERE status = 'failed' ORDER BY started_at DESC LIMIT 10`
- Rerun the failed step manually

### Inspecting Pipeline Runs

```sql
-- Recent runs
SELECT run_id, stage, status, started_at, ended_at, rows_written, error
FROM prediction_gold.pipeline_runs
ORDER BY started_at DESC
LIMIT 20;

-- Failed runs
SELECT *
FROM prediction_gold.pipeline_runs
WHERE status = 'failed'
ORDER BY started_at DESC;
```

### Inspecting Data Quality

```sql
-- Recent quality check failures
SELECT dataset, partition, check_name, status, observed_value, expected
FROM prediction_gold.data_quality_metrics
WHERE status = 'fail'
ORDER BY checked_at DESC
LIMIT 20;
```

## ClickHouse Schema Reference

All Gold tables are created automatically by init scripts in `docker/clickhouse/init/`.

**Dimension tables:**
- `dim_platform`, `dim_market`, `dim_outcome`, `dim_wallet`, `dim_event`, `dim_category`

**Fact tables:**
- `wallet_position_ledger` — Per-fill position accounting records
- `wallet_position_state` — Current position state (ReplacingMergeTree)
- `market_mark_daily` — Daily market marks
- `wallet_pnl_daily` — Daily wallet PnL
- `wallet_mtm_daily` — Daily wallet MTM (watchlist)
- `wallet_position_snapshot_daily` — Daily position snapshots (watchlist)

**Ops metadata tables:**
- `pipeline_runs` — Pipeline run tracking
- `dataset_partitions` — Partition metadata
- `dataset_freshness` — Freshness SLA tracking
- `data_quality_metrics` — Quality check results
- `gold_watchlist` — Wallet watchlist

**TTL policies:**
- Most tables: 90-day TTL on the date column
- `wallet_position_ledger`: 30-day TTL

## Environment Requirements

| Variable | Required | Description |
|----------|----------|-------------|
| `GOLD_BUCKET` | Yes | S3 bucket for Gold Parquet files |
| `CLICKHOUSE_HOST` | No | ClickHouse hostname (default: localhost) |
| `CLICKHOUSE_PORT` | No | ClickHouse native port (default: 9000) |
| `CLICKHOUSE_USER` | No | ClickHouse username (default: default) |
| `CLICKHOUSE_PASSWORD` | No | ClickHouse password (default: empty) |
| `CLICKHOUSE_DATABASE` | No | ClickHouse database (default: prediction_gold) |

AWS credentials must have access to: S3 (read/write for `GOLD_BUCKET`), Glue Catalog (read for Silver tables).
