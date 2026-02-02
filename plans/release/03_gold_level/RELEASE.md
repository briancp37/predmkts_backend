# RELEASE_3.md
## Release 3 — Gold Serving Layer (S3 + ClickHouse)
### Silver → Gold Analytics, Position Accounting, Serving

**Scope:** Everything required to go from **trusted Silver (Iceberg)** to a **production-ready Gold layer** with canonical derived tables in S3 (Parquet) and a hot serving store in ClickHouse for fast queries.
**Non-Goals:** End-user UI, trading strategies, ML models, alerting products, API endpoints (those are Release 4+).

---

## 1) Objective

Release 3 establishes **Gold as the serving and analytics layer**:

- Dual-storage architecture: **S3 Gold (Parquet)** as canonical store, **ClickHouse** as hot serving layer
- Position accounting with average cost basis and per-fill realized PnL
- Daily market marks, wallet metrics, and leaderboards
- On-demand historical snapshot computation via CLI
- Watchlist-driven selective computation for expensive per-wallet tables
- Operational metadata, freshness SLAs, and alerting states
- Lightweight scheduling via EventBridge/cron triggering CLI commands

At the end of Release 3:
> Gold provides fast, query-optimized data for any downstream API or frontend, with S3 as the canonical store and ClickHouse as a TTL-managed hot mirror.

---

## 2) Definition of Done (Exit Criteria)

Release 3 is complete when:

1. ✅ ClickHouse is running (Docker local dev, prod hosting TBD)
2. ✅ Dimension tables are populated from Silver (dim_market, dim_outcome, dim_platform, dim_wallet)
3. ✅ Canonical ID mapping is implemented (market_links.yaml + resolution logic)
4. ✅ Position accounting engine processes both maker + taker sides per fill
5. ✅ `wallet_position_state` reflects current open positions in ClickHouse
6. ✅ `wallet_position_ledger` records per-fill audit trail with realized PnL in S3 Gold
7. ✅ `market_mark_daily` computes daily marks, volume, and liquidity metrics
8. ✅ `wallet_pnl_daily` aggregates realized PnL (sparse, trade-days only)
9. ✅ Watchlist-only tables computed for tracked wallets (mtm_daily, position_snapshot_daily)
10. ✅ On-demand CLI computes and caches historical snapshots to S3 Gold
11. ✅ Ops metadata tables track pipeline runs, partitions, freshness, and quality
12. ✅ Freshness SLAs are defined and alerting states implemented
13. ✅ Gold CLI commands support load, rollup, rebuild with dry-run
14. ✅ EventBridge/cron schedules defined for automated Gold processing
15. ✅ No API/frontend logic leaks into Gold code

---

## 3) Inputs & Outputs

### Inputs (from Release 2)
- Silver Iceberg tables (Polymarket trades, markets, events)
- Silver schemas and deduplication guarantees

### Outputs (Release 3)
- S3 Gold Parquet files (canonical derived tables)
- ClickHouse hot serving tables (TTL-managed subsets)
- Ops metadata and freshness tracking

---

## 4) Architecture

```
Silver (Iceberg/S3) = source of truth
        ↓
Gold compute (Python CLI jobs)
        ↓
S3 Gold (Parquet) = canonical derived tables
        ↓
ClickHouse = hot serving store (TTL-managed subset)
```

### 4.1 S3 Gold Path Convention
```
s3://<GOLD_BUCKET>/gold/<table_name>/day=YYYY-MM-DD/part-*.parquet
```

### 4.2 ClickHouse Hosting
- **Development**: Docker-compose with local ClickHouse
- **Production**: TBD (ClickHouse Cloud Basic or cheap VPS, ~$20/month budget target)
- Code is connection-string agnostic — same logic works against local or remote

### 4.3 Orchestration
- **Lightweight scheduler**: EventBridge/cron triggers CLI commands
- No Dagster in R3. CLI-based execution identical to Bronze/Silver patterns.

---

## 5) Gold Data Products

### 5.1 Global — Computed for All Data

#### A) `market_mark_daily`
Daily canonical mark prices + market activity metrics.

| Property | Value |
|---|---|
| **Canonical store** | S3 Gold (Parquet) |
| **Hot mirror** | ClickHouse, last 90 days |
| **Key** | `(day_utc, platform, market_id, outcome_id)` |

Fields:
- `day_utc` (date, midnight UTC)
- `platform` (polymarket / kalshi)
- `market_id`, `outcome_id`
- `mark_price`
- `volume_usd_24h`
- `liquidity_metric` (open_interest_usd if feasible, else proxy)
- Optional: `trades_count_24h`, `last_trade_price`, `active_wallets_24h`

S3 path: `s3://.../gold/market_mark_daily/day=YYYY-MM-DD/part-*.parquet`

#### B) `wallet_pnl_daily`
Realized PnL only, sparse (rows only when trades_count > 0 that day).

| Property | Value |
|---|---|
| **Canonical store** | S3 Gold (Parquet) |
| **Serving** | ClickHouse, TTL 90 days |
| **Key** | `(day_utc, wallet)` |

Fields:
- `realized_pnl_usd`
- `fees_usd`
- `volume_usd`
- `trades_count`
- Optional: `wins`, `losses`

S3 path: `s3://.../gold/wallet_pnl_daily/day=YYYY-MM-DD/part-*.parquet`

---

### 5.2 Current State — Everyone

#### `wallet_position_state`
Current open positions only. Rows drop when qty = 0.

| Property | Value |
|---|---|
| **Canonical serving** | ClickHouse only (current-state) |
| **History** | NOT stored here |
| **Key** | `(wallet, platform, market_id, outcome_id)` |

Fields:
- `qty` (net shares)
- `avg_cost`
- `cost_basis_usd`
- `last_fill_ts`
- Optional: `first_open_ts`, `fees_lifetime`

---

### 5.3 Watchlist-Only — Selective Computation

Computed only for wallets in the `gold_watchlist` ClickHouse table.

#### A) `wallet_mtm_daily`
Portfolio equity/exposure/unrealized charts for watchlist wallets.

| Property | Value |
|---|---|
| **Canonical store** | S3 Gold (Parquet) |
| **Serving** | ClickHouse, TTL 90 days |
| **Key** | `(day_utc, wallet)` |

Fields:
- `equity_usd` (sum position value)
- `unrealized_pnl_usd`
- `exposure_gross_usd`
- `exposure_net_usd`

S3 path: `s3://.../gold/wallet_mtm_daily/day=YYYY-MM-DD/part-*.parquet`

#### B) `wallet_position_snapshot_daily`
Chart-ready per-position history for watchlist wallets.

| Property | Value |
|---|---|
| **Canonical store** | S3 Gold (Parquet) |
| **Serving** | ClickHouse, TTL 90 days |
| **On-demand** | If missing partitions requested, compute and persist |
| **Key** | `(day_utc, wallet, platform, market_id, outcome_id)` |

Fields:
- `qty`, `avg_cost`, `mark_price`
- `position_value_usd`, `unrealized_pnl_usd`

S3 path: `s3://.../gold/wallet_position_snapshot_daily/day=YYYY-MM-DD/part-*.parquet`

#### C) `wallet_position_ledger`
Per-fill audit trail with before/after state and realized PnL per fill.

| Property | Value |
|---|---|
| **Canonical store** | S3 Gold (Parquet) |
| **Serving** | ClickHouse, TTL 7–30 days (optional) |
| **Key** | `(ts, wallet, platform, market_id, outcome_id)` |

Fields:
- `ts`, `wallet`, `platform`, `market_id`, `outcome_id`
- `side`, `qty_delta`, `price`, `fees_usd`
- `qty_before`, `qty_after`
- `avg_cost_before`, `avg_cost_after`
- `realized_pnl_this_fill_usd`

S3 path: `s3://.../gold/wallet_position_ledger/day=YYYY-MM-DD/part-*.parquet`

---

## 6) Dimension Tables

### 6.1 Tables
- `dim_platform` — static reference (polymarket, kalshi)
- `dim_market` — from Silver markets, includes canonical_market_id
- `dim_outcome` — derived from markets token data (token1/token2 per market)
- `dim_wallet` — discovered from Silver trades (maker + taker addresses)
- `dim_category` — optional, from Silver events

### 6.2 Canonical ID Mapping
- Source: `mappings/market_links.yaml` (cross-platform market mappings)
- Resolution logic maps platform-specific IDs to `canonical_market_id`
- Platform-native IDs remain available alongside canonical IDs

### 6.3 ClickHouse Engine
```sql
ENGINE = ReplacingMergeTree(version)
ORDER BY (primary_key)
```

---

## 7) Position Accounting Rules

### 7.1 Method
**Average cost basis** per `(wallet, platform, market_id, outcome_id)`.

### 7.2 Per-Fill Processing
Each Silver trade (derived from order_filled) produces **2 ledger entries** — one for the maker and one for the taker:

1. Determine each party's side (buy/sell) from `maker_direction` / `taker_direction`
2. For **buys**: increase qty, update weighted average cost
3. For **sells**: decrease qty, compute realized PnL = `qty_delta × (price - avg_cost)`
4. Update `wallet_position_state` (insert/update if qty ≠ 0, remove if qty = 0)
5. Emit a `wallet_position_ledger` row with before/after state + realized PnL
6. Aggregate per-wallet into `wallet_pnl_daily` for that day_utc (realized only)

### 7.3 Formulas
- `realized_pnl = qty_sold × (sell_price - avg_cost)`
- `unrealized_pnl = current_qty × (mark_price - avg_cost)`
- `cost_basis_usd = current_qty × avg_cost`
- `equity_usd = sum(position_value_usd)` across all positions

---

## 8) On-Demand Compute + Caching

### 8.1 CLI Interface
```bash
# Compute missing position snapshots for a wallet
prediction-data gold compute-snapshot --wallet 0xABC... --start-date 2024-01-01 --end-date 2024-12-31

# Dry run
prediction-data gold compute-snapshot --wallet 0xABC... --start-date 2024-01-01 --end-date 2024-12-31 --dry-run
```

### 8.2 Computation Logic
Inputs:
- `market_mark_daily` (S3)
- `wallet_position_snapshot_daily` (if exists), else reconstruct from:
  - `wallet_position_ledger` (S3) and/or Silver facts

Output caching:
- Always write computed missing partitions to S3 Gold (`wallet_position_snapshot_daily`)
- Optionally load into ClickHouse if within hot TTL window (last 90 days)

### 8.3 Guardrails
- Chunk by day range
- Async job for very large ranges (future)
- Idempotent partition overwrite

---

## 9) ClickHouse Serving TTL Recommendations

| Table | TTL |
|---|---|
| `wallet_pnl_daily` | 90 days |
| `wallet_position_snapshot_daily` (watchlist) | 90 days |
| `wallet_mtm_daily` (watchlist) | 90 days |
| `wallet_position_ledger` (watchlist) | 7–30 days (optional) |
| `wallet_position_state` | No TTL (current only) |
| `market_mark_daily` | 90 days |

---

## 10) Ops Metadata & Freshness SLAs

### 10.1 Metadata Tables (ClickHouse)

**`pipeline_runs`**
- `run_id`, `stage` (bronze/silver/gold), `started_at`, `ended_at`, `status`
- `input_snapshot_id`, `output_snapshot_id`, `rows_written`, `bytes_written`, `error`

**`dataset_partitions`**
- `dataset`, `partition_day_utc`, `row_count`, `max_event_ts`, `written_at`, `run_id`

**`dataset_freshness`**
- `dataset`, `last_success_at`, `expected_lag_seconds`, `actual_lag_seconds`
- `state` (fresh/stale/broken), `last_run_id`

**`data_quality_metrics`**
- `dataset`, `partition`, `check_name`, `status`, `observed_value`, `expected`, `run_id`

### 10.2 Freshness SLAs (Defaults)

| Dataset | SLA |
|---|---|
| `market_mark_daily` | Written by 00:05 UTC daily |
| `wallet_pnl_daily` | Written by 00:10 UTC daily |
| `wallet_mtm_daily` (watchlist) | Written by 00:15 UTC daily |
| `wallet_position_snapshot_daily` (watchlist) | Written by 00:15 UTC daily |
| `wallet_position_state` | Document cadence (batch for R3) |

### 10.3 Alerting States
- **Fresh**: within SLA
- **Stale**: > SLA and ≤ 2× SLA
- **Broken**: > 2× SLA or last run failed

---

## 11) CLI Contract (Release 3)

```bash
# Load dimensions from Silver to Gold
prediction-data gold load-dims [--dry-run]

# Process trades into position ledger + state
prediction-data gold process-trades --dt YYYY-MM-DD [--dry-run]
prediction-data gold process-trades --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Compute market marks
prediction-data gold compute-marks --dt YYYY-MM-DD [--dry-run]

# Compute wallet metrics (pnl, mtm for watchlist)
prediction-data gold compute-wallet-metrics --dt YYYY-MM-DD [--dry-run]

# On-demand snapshot computation
prediction-data gold compute-snapshot --wallet ADDR --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Load data from S3 Gold into ClickHouse
prediction-data gold ch-load --table TABLE [--lookback-days N] [--dry-run]

# Rebuild a Gold table from Silver
prediction-data gold rebuild --table TABLE --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Run all daily Gold processing
prediction-data gold daily-run [--dry-run]
```

---

## 12) Layering Note

All derived analytics tables (`*_daily`, `*_ledger`, snapshots) belong in **S3 Gold**, not Silver. Silver remains normalized facts and dimensions only.

---

## 13) Explicit Non-Goals (Not Built in R3)

- API endpoints (R4)
- Frontend UI (R4)
- Alerts / notifications (R4)
- Strategy signals (R4)
- ML models (R4)
- User auth / permissions (R4)
- Dagster orchestration (deferred — CLI + cron is sufficient)
- Real-time / streaming ingestion

---

## 14) Release 4 Preview

Release 4 will introduce:
- REST API layer over Gold ClickHouse tables
- Frontend / dashboard
- Alerts and notifications
- Strategy signals and ML features
- User authentication and permissions
- SLAs for external consumers

---

## 15) Final Rule

> **Gold is convenience, not truth.**
> Silver is truth.
> Bronze is history.

Release 3 exists to make truth *fast and usable*.
