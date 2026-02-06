# Release 06: Quant Analytics (Black-Scholes Style)

## Overview

Implement quantitative analytics for Polymarket markets using a Black-Scholes analogue framework. This release computes "belief volatility" in log-odds space, detects jumps in probability movements, and provides sophisticated risk metrics for prediction markets.

The core model treats market prices as risk-neutral probabilities and models their evolution using a **jump-diffusion process on log-odds**:

```
dx_t = μ(t,x_t)dt + σ_b(t,x_t)dW_t + dJ_t
```

Where:
- `x_t = logit(p_t) = log(p_t / (1-p_t))` is the log-odds of the probability
- `σ_b` is the **belief volatility** (diffusive volatility in log-odds space)
- `J_t` is a jump process capturing sudden probability shifts
- `μ` is constrained so probability is approximately a martingale

## Goals

1. **Data Foundation** - Fetch and store market metadata, trades, and optional order book data
2. **Price Series Construction** - Build clean VWAP price series with proper bucketing and log-odds transformation
3. **Core Volatility Metrics** - Compute realized variance and belief volatility using truncated RV and bipower variation
4. **Jump Detection** - Identify and characterize jumps in probability movements
5. **Advanced Metrics** - Corridor variance, logistic Greeks, variance forecasting, martingale drift
6. **Order Book Integration** - Optional enhancement using bid/ask spreads for better price estimates
7. **API & Reporting** - Expose metrics via REST API with proper validation

## Mathematical Framework

### Log-Odds Transformation

```
Probability to log-odds:   x = logit(p) = log(p / (1-p))
Log-odds to probability:   p = S(x) = 1 / (1 + e^(-x))
```

### Key Metrics

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| Realized Variance | `RV^x = Σ(Δx_k)²` | Total variation in log-odds |
| Belief Volatility | `σ_b = sqrt(TRV^x / T)` | Diffusive volatility (jumps excluded) |
| Jump Intensity | `λ = N_J / T` | Jumps per year |
| Logistic Delta | `Δ_x = p(1-p)` | Sensitivity of p to log-odds |
| Logistic Gamma | `Γ_x = p(1-p)(1-2p)` | Convexity in log-odds |
| Martingale Drift | `μ = -½(1-2p)σ_b²` | Drift ensuring p is martingale |

### Volatility Estimation Methods

1. **Truncated Realized Variance (TRV)** - Exclude large moves beyond threshold:
   ```
   threshold θ = c × MAD,  where c ∈ [5, 10]
   TRV = Σ(Δx_k)² × 1{|Δx_k| ≤ θ}
   ```

2. **Bipower Variation (BV)** - Robust to jumps:
   ```
   BV = (π/2) × Σ|Δx_k| × |Δx_{k-1}|
   ```

### Jump Detection

Flag increment as jump if:
```
|Δx_k| > m × σ_b × sqrt(Δt),  where m ∈ [5, 10]
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           QUANT MODULE                                          │
│                                                                                  │
│  src/prediction_data/quant/                                                     │
│  ├── models.py              # Pydantic models for metrics                       │
│  ├── data/                                                                      │
│  │   ├── market_meta.py     # Fetch market metadata (Gamma API)                │
│  │   ├── trades.py          # Fetch trade history (CLOB API)                   │
│  │   └── orderbook.py       # Optional: fetch order book snapshots             │
│  ├── preprocessing/                                                             │
│  │   ├── price_series.py    # VWAP bucketing, forward-fill, clamping           │
│  │   └── transforms.py      # Log-odds transformation, increments              │
│  ├── metrics/                                                                   │
│  │   ├── realized_variance.py   # RV, rolling windows                          │
│  │   ├── belief_volatility.py   # TRV, bipower variation                       │
│  │   ├── jumps.py               # Jump detection, intensity, variance          │
│  │   ├── greeks.py              # Logistic Delta, Gamma                        │
│  │   ├── corridor.py            # Corridor variance                            │
│  │   └── forecast.py            # EWMA variance forecasting                    │
│  ├── pipeline.py            # End-to-end metric computation                    │
│  └── cli.py                 # CLI commands for quant metrics                   │
│                                                                                  │
│  API Endpoints (src/prediction_data/api/quant/):                                │
│  ├── router.py              # GET /api/v1/quant/markets/{id}/metrics           │
│  ├── schemas.py             # API response schemas                              │
│  └── service.py             # Business logic layer                              │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                          │
│                                                                                  │
│  ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐ │
│  │   Gamma API         │    │   CLOB API          │    │   ClickHouse        │ │
│  │   (market meta)     │    │   (trades, book)    │    │   (storage)         │ │
│  │                     │    │                     │    │                     │ │
│  │   /markets/{id}     │    │   /data/trades      │    │   pm_market_meta    │ │
│  │   → condition_id    │    │   /book             │    │   pm_trades_raw     │ │
│  │   → asset_ids       │    │   → trade tape      │    │   pm_book_snapshots │ │
│  │   → outcomes        │    │   → bid/ask         │    │   pm_quant_metrics  │ │
│  └─────────────────────┘    └─────────────────────┘    └─────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Data Model

### `pm_market_meta` (ClickHouse)
```sql
CREATE TABLE pm_market_meta (
    condition_id String,
    gamma_market_id String,
    slug String,
    question String,
    outcomes Array(String),
    asset_ids Array(String),
    end_ts DateTime64(3) NULLABLE,
    status String,  -- active/closed/resolved
    tick_size Decimal(18,8) NULLABLE,
    min_order_size Decimal(18,8) NULLABLE
) ENGINE = ReplacingMergeTree()
ORDER BY condition_id;
```

### `pm_trades_raw` (ClickHouse)
```sql
CREATE TABLE pm_trades_raw (
    trade_id String,
    condition_id String,
    asset_id String,
    side String,  -- BUY/SELL
    price Decimal(18,8),
    size Decimal(18,8),
    match_ts DateTime64(3),
    maker_order_id String NULLABLE,
    taker_order_id String NULLABLE,
    fee_rate_bps UInt16 NULLABLE
) ENGINE = ReplacingMergeTree()
ORDER BY (condition_id, asset_id, match_ts, trade_id);
```

### `pm_book_snapshots` (Optional, ClickHouse)
```sql
CREATE TABLE pm_book_snapshots (
    condition_id String,
    asset_id String,
    snapshot_ts DateTime64(3),
    best_bid Decimal(18,8),
    best_ask Decimal(18,8),
    spread Decimal(18,8),
    mid Decimal(18,8),
    tick_size Decimal(18,8),
    min_order_size Decimal(18,8)
) ENGINE = ReplacingMergeTree()
ORDER BY (condition_id, asset_id, snapshot_ts);
```

### `pm_quant_metrics` (ClickHouse)
```sql
CREATE TABLE pm_quant_metrics (
    condition_id String,
    asset_id String,
    computed_at DateTime64(3),
    window_seconds UInt32,  -- 3600, 86400, 604800

    -- State
    current_p Decimal(18,8),
    current_x Float64,
    time_to_resolution_seconds Int64 NULLABLE,

    -- Realized variability
    realized_variance Float64,
    realized_vol_ann Float64,

    -- Belief volatility
    belief_vol_trv Float64,
    belief_vol_bipower Float64,

    -- Jumps
    jump_count UInt32,
    jump_intensity_ann Float64,
    jump_mean_abs Float64,
    jump_variance Float64,
    jump_qv_share Float64,

    -- Greeks
    delta_x Float64,
    gamma_x Float64,

    -- Corridor
    corridor_rv Float64,
    corridor_vol Float64

) ENGINE = ReplacingMergeTree()
ORDER BY (condition_id, asset_id, window_seconds, computed_at);
```

## Sprints

| Sprint | Name | Focus | Dependencies |
|--------|------|-------|--------------|
| 00 | data_foundation | Market meta, trade fetching, storage tables | None |
| 01 | price_series_construction | VWAP, bucketing, log-odds transform | 00 |
| 02 | core_volatility_metrics | Realized variance, belief volatility | 01 |
| 03 | jump_detection | Jump flags, intensity, variance | 02 |
| 04 | advanced_metrics | Corridor variance, Greeks, EWMA, drift | 02, 03 |
| 05 | order_book_integration | Book snapshots, midprice, spread metrics | 00 (optional) |
| 06 | api_and_reporting | REST endpoints, CLI, validation | 01-04 |

### Sprint Dependency Graph

```
┌─────────────────────────────────────────────┐
│     Sprint 00: Data Foundation              │
│     (market meta, trades, tables)           │
└─────────────────────┬───────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│ Sprint 01       │     │ Sprint 05       │
│ Price Series    │     │ Order Book      │
│ (VWAP, logit)   │     │ (optional)      │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│ Sprint 02       │
│ Core Volatility │
│ (RV, σ_b)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Sprint 03       │
│ Jump Detection  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Sprint 04       │
│ Advanced Metrics│
│ (Greeks, etc.)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Sprint 06       │
│ API & Reporting │
└─────────────────┘
```

**Parallelization:**
- Sprint 05 (Order Book) is optional and can run in parallel with 01-04
- Sprints 01-04 are sequential (each builds on previous)
- Sprint 06 depends on 01-04 completion

## Key Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `bin_seconds` | 30 | 10-300 | Time bucket width |
| `max_gap_seconds` | 1800 | 300-7200 | Max forward-fill gap |
| `epsilon` | 1e-6 | 1e-8 to 1e-4 | Price clamping bound |
| `jump_threshold_c` | 6 | 5-10 | Jump detection multiplier |
| `mad_scale` | 1.4826 | fixed | MAD to std conversion |
| `corridor_low` | 0.35 | 0.1-0.45 | Corridor lower bound |
| `corridor_high` | 0.65 | 0.55-0.9 | Corridor upper bound |
| `ewma_halflife` | 20 | 10-100 | EWMA decay (observations) |

## Exit Criteria

- [ ] Market metadata fetching works for any condition_id or slug
- [ ] Trade history fetching handles pagination and stores to ClickHouse
- [ ] VWAP price series construction with configurable bin width
- [ ] Log-odds transformation with proper clamping
- [ ] Realized variance computed for 1h, 1d, 7d windows
- [ ] Belief volatility via both TRV and bipower methods
- [ ] Jump detection identifies significant moves
- [ ] Jump metrics: count, intensity, mean size, variance
- [ ] Logistic Greeks (Delta, Gamma) computed
- [ ] Corridor variance for configurable bounds
- [ ] EWMA variance forecasting
- [ ] Martingale drift estimation
- [ ] REST API endpoints for metrics
- [ ] CLI commands for computing metrics
- [ ] Validation: empirical E[Δp] ≈ 0 after jump filtering
- [ ] Optional: order book snapshot collection

## API Endpoints

```
GET /api/v1/quant/markets/{condition_id}/metrics
  Query: windows=1h,1d,7d, bin_seconds=30
  Response: {
    market: { condition_id, question, current_p, time_to_resolution },
    metrics: {
      "1h": { realized_variance, belief_vol_trv, belief_vol_bipower, jump_count, ... },
      "1d": { ... },
      "7d": { ... }
    },
    greeks: { delta_x, gamma_x },
    corridor: { low: 0.35, high: 0.65, rv, vol }
  }

GET /api/v1/quant/markets/{condition_id}/timeseries
  Query: start_ts, end_ts, bin_seconds=30
  Response: {
    points: [{ ts, p, x, dx, sigma_b_rolling, is_jump }, ...]
  }

GET /api/v1/quant/markets/{condition_id}/jumps
  Query: window=7d, min_size=0
  Response: {
    jumps: [{ ts, dx, p_before, p_after, size_dollars }, ...]
  }
```

## CLI Commands

```bash
# Compute metrics for a market
prediction-data quant compute --condition-id <id> --windows 1h,1d,7d

# Backfill trade history
prediction-data quant backfill-trades --condition-id <id> --start-date 2024-01-01

# Fetch and store market metadata
prediction-data quant fetch-meta --condition-id <id>

# Start order book snapshot collection (optional)
prediction-data quant collect-book --condition-id <id> --interval-seconds 30
```

## Deferred / Phase 2

- WebSocket streaming for real-time volatility updates
- Full parametric jump distribution fitting (normal, double-exponential)
- Multi-market correlation analysis
- Volatility surface by time-to-resolution
- Market regime detection (trending vs mean-reverting)
- ML-based volatility forecasting
- Options-style implied volatility (if synthetic options exist)
