# RELEASE_2.md
## Release 2 — Silver Lakehouse (Iceberg) Fully Working  
### Bronze → Silver Normalization, Deduplication, Quality Gates

**Scope:** Everything required to go from **immutable Bronze** to a **correct, queryable, production-grade Silver layer** using **Iceberg**.  
**Non-Goals:** Gold / ClickHouse serving, user-facing APIs, dashboards, strategy analytics.

---

## 1) Objective

Release 2 establishes **Silver as the source of truth for clean data**:

- Typed, normalized, and deduplicated datasets
- Event-time–based storage with late-arrival tolerance
- ACID guarantees via Iceberg
- Manifest-driven, idempotent processing
- Enforced data contracts and quality checks
- Backfill-safe and rebuildable by partition

At the end of Release 2, Silver must be **trustworthy enough** that:
> Any downstream consumer (Gold, ML, analytics) can rely on Silver without re-checking raw data.

---

## 2) Definition of Done (Exit Criteria)

Release 2 is complete when:

1. ✅ Iceberg catalog (Glue) is live and versioned
2. ✅ Silver tables exist for Polymarket and Kalshi entities
3. ✅ Bronze → Silver processing is **manifest-driven**
4. ✅ Deduplication rules are enforced in Silver
5. ✅ Late-arriving data is handled correctly
6. ✅ Data quality checks run and fail loudly
7. ✅ Silver partitions can be **backfilled and rebuilt**
8. ✅ Iceberg maintenance jobs are automated
9. ✅ No Gold/ClickHouse logic leaks into Silver code

---

## 3) Inputs & Outputs

### Inputs (from Release 1)
- Bronze JSONL.gz files in S3
- `manifest.json` per run

### Outputs (Release 2)
- Iceberg tables in S3 (Parquet)
- Clean, typed, deduplicated rows
- Versioned snapshots and metadata

---

## 4) Silver Data Model

### 4.1 Entity Coverage (Release 2)

| Platform | Entity | Silver Table | Notes |
|--------|-------|-------------|-------|
| Polymarket | trades | `silver_polymarket.trades` | Derived from Bronze `order_filled` (see below) |
| Polymarket | markets | `silver_polymarket.markets` | From Bronze markets (Gamma API) |
| Polymarket | events | `silver_polymarket.events` | From Bronze events (Gamma API) |
| Kalshi | trades | `silver_kalshi.trades` | Scaffold only (no data yet) |
| Kalshi | markets | `silver_kalshi.markets` | Scaffold only (no data yet) |
| Kalshi | events | `silver_kalshi.events` | Scaffold only (no data yet) |

> Canonical cross-platform tables are **optional** in R2 and may be partial.
> Kalshi tables are scaffolded (schema + table creation) but not populated until Kalshi data is available.

### 4.2 Polymarket Trades Derivation (order_filled → trades)

Polymarket Silver trades are **computed from Bronze `order_filled` events**, not ingested directly. Each `OrderFilledEvent` is a raw on-chain swap between a maker and a taker. The transformation:

1. **Resolve non-USDC asset** to a market and side. Load a markets reference table with token1/token2 asset IDs per market. Melt/unpivot into `(market_id, side, asset_id)` lookup. For each event, identify which of `makerAssetId`/`takerAssetId` is not `"0"` — that's the conditional token. Join against lookup to get `market_id` and side (token1/token2).
2. **Label each party's asset.** The party with asset ID `"0"` is providing USDC; the other provides the conditional token.
3. **Scale amounts.** Divide `makerAmountFilled` and `takerAmountFilled` by 1e6 to convert from base units to USDC/token decimal values.
4. **Determine trade direction.** Taker providing USDC = buying the token. Taker providing the token = selling.
5. **Derive price and amounts.** `usd_amount` = USDC side's fill amount. `token_amount` = other side's fill amount. `price = usd_amount / token_amount`.
6. **Output columns:** `timestamp`, `market_id`, `maker`, `taker`, `nonusdc_side` (token1/token2), `maker_direction`, `taker_direction`, `price`, `usd_amount`, `token_amount`, `transactionHash`.

---

## 5) Iceberg Storage Design

### 5.1 Catalog
- **AWS Glue Catalog**
- One database per layer:
  - `prediction_silver`

### 5.2 Table Properties (Standard)
- Format: Parquet
- Compression: ZSTD or Snappy
- Target file size: **128–512MB**
- Write mode: Copy-on-write

### 5.3 Partitioning (Critical Decision)

**Default partition spec:**
```

days(event_ts)

```

Reasons:
- Event-time queries dominate analytics
- Avoids small-file explosion
- Supports late-arriving data

### 5.4 Sorting / Clustering (Recommended)
Within partitions:
- Primary: `platform_market_id`
- Secondary: `event_ts`

---

## 6) Bronze → Silver Processing Model

### 6.1 Manifest-Driven Execution

Silver processing is triggered by Bronze `manifest.json`.

For each manifest:
1. Read manifest metadata
2. Load referenced Bronze files
3. Normalize raw JSON → typed records
4. Deduplicate
5. Write to Iceberg
6. Emit processing metadata

**Unit of work:**
```

(platform, entity, dt, run_id)

````

This makes the system:
- idempotent
- restart-safe
- parallelizable

---

## 7) Normalization Rules

### 7.1 What Silver *does*
- Enforce schemas (types, nullability)
- Normalize field names
- Convert timestamps to UTC
- Normalize numeric types
- Add ingestion metadata

### 7.2 What Silver *does not do*
- Cross-platform joins (mostly)
- Business logic
- Analytics
- Aggregations

Silver answers:
> “What happened, cleanly and unambiguously?”

---

## 8) Deduplication Strategy (Mandatory)

### 8.1 Deduplication Keys (Examples)

| Entity | Unique Key |
|------|------------|
| trades | `(platform, platform_trade_id)` |
| markets | `(platform, platform_market_id, updated_at)` |

If a platform does not provide stable IDs:
- Use a **content hash** over stable fields
- Document the strategy explicitly

### 8.2 Conflict Resolution
- **Latest wins** by `updated_at` or `event_ts`
- Conflicts are logged to a Silver-side conflict log

---

## 9) Late-Arriving & Corrected Data

Silver **must tolerate**:
- Trades arriving hours/days late
- Market metadata corrections
- Reordered API results

### Mechanism:
- Event-time partitioning
- Iceberg ACID snapshots
- Upsert logic keyed by dedupe keys

No data is ever silently dropped.

---

## 10) Data Quality Gates (Release 2 Requirement)

### 10.1 Minimum Checks (Per Table)
- Non-null critical columns
- Uniqueness of dedupe key
- Valid timestamp ranges
- Referential sanity (e.g., trade → market exists if applicable)

### 10.2 Failure Behavior
- **Fail the Silver job**
- Do not partially commit
- Record failure metadata

Silver correctness > availability.

---

## 11) Iceberg Maintenance (Mandatory)

### 11.1 Scheduled Jobs
| Task | Cadence |
|----|--------|
| File compaction | daily |
| Snapshot expiration | daily or weekly |
| Orphan cleanup | weekly |

### 11.2 Why This Matters
Without maintenance:
- Metadata explodes
- Queries slow down
- Storage costs rise silently

Maintenance is part of “done.”

---

## 12) Backfills & Rebuilds

### 12.1 Backfill Definition
Reprocessing historical Bronze data into Silver.

### 12.2 Backfill Rules
- Driven by manifests
- Re-runnable
- Partition-scoped
- No special code paths

Example:
```bash
prediction-data silver polymarket-trades --dt 2025-11-01
````

### 12.3 Rebuild Scenarios

* Schema change
* Deduplication bug
* Late correction

Rebuilds are expected and supported.

---

## 13) Orchestration (Release 2)

### 13.1 Triggering Model

| Stage  | Trigger                              |
| ------ | ------------------------------------ |
| Bronze | EventBridge + ECS                    |
| Silver | **Event-driven** (manifest detected) |

### 13.2 Orchestrator Options

* **Dagster (recommended for R2)**

  * Sensors watch for new manifests
  * Partition-aware backfills
  * Clear lineage
* EventBridge + SQS + worker (acceptable but more plumbing)

Dagster becomes valuable **starting in Release 2**.

---

## 14) Observability & Metadata

Silver jobs must emit:

* input manifest
* output Iceberg snapshot ID
* rows read / written
* deduped row count
* quality check results
* duration

Metadata storage target:

* ClickHouse (preferred)
* or structured logs for MVP

---

## 15) Explicit Non-Goals (Still Not Built)

* ClickHouse serving tables
* API endpoints
* Real-time analytics
* User-facing dashboards
* Strategy signals

Silver is **not** a serving layer.

---

## 16) Release 3 Preview (Gold)

Release 3 will introduce:

* ClickHouse serving tables
* Rollups and aggregates
* Leaderboards and metrics
* API-ready schemas
* SLAs and latency targets

But only once Silver is **boring and correct**.

---

## 17) Final Rule

> **Silver is the contract.**
> Bronze is history.
> Gold is convenience.

Release 2 exists to make Silver unquestionable.

