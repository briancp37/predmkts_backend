# RELEASE.md
## Release 1 (MVP) — Bronze Bootstrapping + Automated Updates  
### Orchestration: **AWS EventBridge + ECS/Fargate**

**Scope:** Bootstrapping → Bronze layer fully set up and continuously populated for **Polymarket** and **Kalshi**, with automated updates using **AWS-native scheduling**.  
**Non-Goals:** Silver (Iceberg), Gold (ClickHouse), canonical IDs, deduplication, analytics, UI.

---

## 1) Objective

Release 1 establishes a **correct, replayable, production-grade Bronze layer** that:

- Ingests **raw data** from Polymarket and Kalshi
- Runs **fully automated** on schedules (no manual intervention)
- Is **append-only, immutable, auditable, and re-runnable**
- Uses **AWS EventBridge + ECS/Fargate** for orchestration (no always-on services)
- Creates a foundation that will not need to be reworked for Silver/Gold later

---

## 2) Definition of Done (Exit Criteria)

Release 1 is complete when:

1. ✅ S3 Bronze bucket exists with **versioning enabled**
2. ✅ Polymarket `trades`, `markets`, and `events` ingestion runs on schedule via EventBridge
3. ✅ Kalshi `trades`, `markets`, and `events` ingestion runs on schedule via EventBridge
4. ✅ Each run writes:
   - raw `part-000.jsonl.gz`
   - a `manifest.json`
5. ✅ Ingestion is **restart-safe** (no overwrites, no mutable state)
6. ✅ Backfills can be executed safely via the same ECS task definitions
7. ✅ CloudWatch logs show successful, retryable, observable runs
8. ✅ No Silver/Gold assumptions exist in Bronze code

---

## 3) Platforms & Entities (Release 1)

### Platforms
- Polymarket
- Kalshi

### Entities (MVP)
| Platform | Entity | Type | Ingestion model | Recommended cadence |
|---|---|---|---|---|
| Polymarket | `trades` | high-frequency | date-scoped (per-day) | every 5 minutes |
| Polymarket | `markets` | catalog | full fetch (not date-scoped) | every 1–6 hours |
| Polymarket | `events` | catalog | full fetch (not date-scoped) | every 1–6 hours |
| Kalshi | `trades` | high-frequency | date-scoped (per-day) | every 5 minutes |
| Kalshi | `markets` | slowly-changing | date-scoped (per-day) | every 1–6 hours |
| Kalshi | `events` | slowly-changing | date-scoped (per-day) | every 1–6 hours |
| Polymarket | `order_filled` | high-frequency | date-scoped (per-day) | every 5 minutes |

**Catalog vs date-scoped entities:**
- **Date-scoped** (trades): Fetched per-day using timestamp filters. Backfill iterates over each day in the range.
- **Catalog** (Polymarket markets/events): Supports two modes. **Full snapshot**: fetches every record via the Gamma API (~360k markets, ~176k events), stored with `snapshot_type: "snapshot"`. **Incremental delta**: fetches only records updated since the last run by paginating with `order=updatedAt&ascending=false` and stopping at the previous cursor, stored with `snapshot_type: "delta"`. Catchup uses incremental mode by default; `--full` forces a full snapshot.

> Explicitly out of scope in R1: order books, transfers, canonicalization.

**On-chain data (Goldsky subgraph):**
- **`order_filled`**: Fetched from Goldsky-hosted orderbook subgraph (GraphQL). Date-scoped using timestamp filters. Schema: `OrderFilledEvent` (transactionHash, orderHash, timestamp, maker, taker, makerAssetId, takerAssetId, makerAmountFilled, takerAmountFilled, fee). Historical backfill reads from a monolithic parquet file at `s3://polymarket-bcp892/raw/polymarket/order_filled.parquet` (~15 GB, 313M rows). The backfill script streams row groups to filter by date without loading the full file into memory. Asset IDs (stored as float-notation strings due to precision loss) are resolved to full-precision token IDs via a mapping built from bronze markets JSONL data. Records from parquet are missing `orderHash`, `fee`, and `id` (stored as null).

---

## 4) Bronze Storage Contract (Non-Negotiable)

### 4.1 Storage rules
- **S3 only**
- **Append-only**
- **Immutable forever**
- Never overwrite or mutate existing objects

### 4.2 File format
- JSON Lines (`.jsonl`)
- Gzipped (`.gz`)
- UTF-8
- One JSON object per line
- Raw API payloads (minimal write-safe normalization only)

### 4.3 S3 key layout (Required)

```

s3://<BRONZE_BUCKET>/bronze/<platform>/<entity>/dt=YYYY-MM-DD/run_id=<uuid>/
part-000.jsonl.gz
manifest.json

```

Example:
```

s3://prediction-bronze/bronze/polymarket/trades/dt=2026-01-27/run_id=<uuid>/part-000.jsonl.gz

````

---

## 5) Run Model & Idempotency

### 5.1 `run_id`
- Every ECS task invocation generates a UUID `run_id`
- `run_id` is included in:
  - S3 prefix
  - manifest.json
  - CloudWatch logs

### 5.2 Idempotency rules
- Bronze never overwrites data
- Retries create **new run_ids**
- Duplicate raw rows are allowed in Bronze
- Deduplication is deferred to Silver (future release)

This ensures:
- safe retries
- deterministic reprocessing
- complete forensic history

### 5.3 Incremental ingestion

Two entity types support **incremental ingestion**:

**order_filled (timestamp-based):** Each run fetches only records newer than the last known timestamp via `timestamp_gte` on the Goldsky subgraph. Avoids massive data duplication when running on a frequent schedule.

**Catalog entities — markets & events (updatedAt-based):** Each run fetches only records that changed since the last run by paginating with `order=updatedAt&ascending=false` and stopping when a record's `updatedAt` is older than the previous cursor. Delta partitions are tagged with `snapshot_type: "delta"` in the manifest; full snapshots use `snapshot_type: "snapshot"`. Existing manifests without `snapshot_type` default to `"snapshot"` for backwards compatibility.

Common mechanics:
- The latest cursor is discovered by reading the most recent manifest's `source.latest_timestamp` field (or falling back to scanning the data file for order_filled).
- Discovery uses S3 delimiter listing (`list_prefixes`) for fast partition enumeration — no full key scan required.
- New records are appended as a new `run_id` directory (Bronze append-only contract preserved).
- The `backfill catchup` command uses incremental mode for both `order_filled` and catalog entities by default. Use `--full` to force a full snapshot for catalog entities.
- The `status coverage` command only checks date-scoped bronze entities (kalshi/trades, polymarket/order_filled). Catalog entities (markets, events) and polymarket/trades (not in bronze) are excluded.
- The `status latest` command provides a fast check of the most recent date partition per entity using S3 delimiter listing.

---

## 6) `manifest.json` Contract (Required)

Each ingestion run **must** write a manifest.

### 6.1 Schema (v1)
```json
{
  "run_id": "uuid",
  "platform": "polymarket | kalshi",
  "entity": "trades | markets | events",
  "dt": "YYYY-MM-DD",
  "generated_at": "ISO-8601 UTC timestamp",
  "files": [
    { "bucket": "string", "key": "string" }
  ],
  "row_count": 12345,
  "source": {
    "api_base_url": "string",
    "pagination": "string | null",
    "cursor": "string | null",
    "latest_timestamp": "integer | null",
    "snapshot_type": "snapshot | delta (default: snapshot)"
  }
}
````

### 6.2 Why manifests are mandatory

* Enable precise backfills and replays
* Provide auditability and reconciliation
* Become future triggers for Silver (Release 2)

**No manifest = failed run.**

---

## 7) API Ingestion Best Practices (Bronze)

### 7.1 HTTP behavior

* Use a shared HTTP client layer:

  * `httpx`
  * timeouts
  * retries with exponential backoff + jitter
* Retry on:

  * 429 (rate limit)
  * 503 / transient 5xx
  * network errors

### 7.2 Pagination & cursors

* Platform-specific logic lives in `bronze/<platform>/`
* Cursor progress may be written to `manifest.source.cursor`
* Cursor state is **not persisted across runs** in R1

### 7.3 Defensive assumptions

* APIs may return partial data
* APIs may reorder results
* APIs may change paging limits

Bronze is designed to tolerate all of this.

---

## 8) Scheduling & Automation (EventBridge + ECS)

### 8.1 Why EventBridge + ECS/Fargate

* No always-on services
* IAM-based security (no UI to protect)
* Highly reliable scheduling
* Easy retries and observability via CloudWatch
* Clean separation: **logic in code, scheduling in AWS**

This is the **best-practice AWS-native approach** for a Bronze-only MVP.

---

### 8.2 Architecture Overview

```
EventBridge Schedule
        ↓
ECS Task (Fargate)
        ↓
prediction-data CLI
        ↓
S3 Bronze (jsonl.gz + manifest.json)
        ↓
CloudWatch Logs
```

Each scheduled run is **stateless**, **short-lived**, and **self-contained**.

---

### 8.3 ECS Task Design

* **One task definition per ingestion type**, or a parameterized task:

  * `PLATFORM=polymarket`
  * `ENTITY=trades`
  * `DT=$(date)`
* Task runs exactly **one CLI command**, then exits
* Failures surface via:

  * non-zero exit code
  * CloudWatch logs
  * EventBridge retry / alarm policies

---

### 8.4 Recommended Schedules (America/Chicago)

| Job                | Schedule        |
| ------------------ | --------------- |
| Polymarket trades  | every 5 minutes |
| Kalshi trades      | every 5 minutes |
| Polymarket markets | every 1–6 hours |
| Polymarket events  | every 1–6 hours |
| Kalshi markets     | every 1–6 hours |
| Kalshi events      | every 1–6 hours |

---

### 8.5 Backfills with EventBridge + ECS

Backfills use the **same ECS task**, manually invoked:

```bash
aws ecs run-task \
  --cluster prediction-data \
  --task-definition ingest-polymarket-trades \
  --overrides '{"containerOverrides":[{"name":"app","command":["prediction-data","ingest","polymarket-trades","--dt","2025-11-01"]}]}'
```

Backfill rules:

* No overwrite
* New `run_id` per invocation
* Manifest required
* Identical logic to scheduled runs

---

## 9) CLI Contract (Release 1)

All ingestion is driven via CLI.

Required commands:

```bash
prediction-data ingest polymarket-trades --dt YYYY-MM-DD
prediction-data ingest polymarket-markets --dt YYYY-MM-DD
prediction-data ingest polymarket-events --dt YYYY-MM-DD
prediction-data ingest kalshi-trades --dt YYYY-MM-DD
prediction-data ingest kalshi-markets --dt YYYY-MM-DD
prediction-data ingest kalshi-events --dt YYYY-MM-DD
prediction-data ingest polymarket-order-filled --dt YYYY-MM-DD

# Monitoring & status
prediction-data status coverage --start-date YYYY-MM-DD --end-date YYYY-MM-DD [--platform] [--entity]
prediction-data status latest [--platform] [--entity]
prediction-data status runs [--platform] [--entity] [--dt YYYY-MM-DD] [--last N]
prediction-data status show-run <run_id>
prediction-data status validate --start-date YYYY-MM-DD --end-date YYYY-MM-DD [--platform] [--entity]

# Catchup (auto-detect latest data, backfill to present)
prediction-data backfill catchup [--platform] [--entity] [--bucket] [--dry-run]
```

CLI guarantees:

* prints `run_id` on success
* non-zero exit code on failure
* never mutates existing Bronze data

---

## 10) Logging & Observability

### Required logging fields

* platform
* entity
* dt
* run_id
* row_count
* API retries/errors
* duration

### Observability tools

* CloudWatch Logs
* EventBridge failure metrics
* ECS task exit codes

No additional observability infrastructure is required in R1.

---

## 11) Explicit Non-Goals (Do NOT build in R1)

* Iceberg / Silver transforms
* ClickHouse / Gold loaders
* Canonical IDs
* Deduplication
* Schema enforcement beyond write-safety
* Analytics, leaderboards, dashboards
* Dagster, sensors, or pipeline UIs

---

## 12) Release 2 Preview (Not Implemented)

Release 2 will add:

* Iceberg Silver tables
* Manifest-driven processing
* Data quality gates
* Canonical IDs
* Dagster (or similar) for asset orchestration

---

## 13) Final Rule

**Bronze is law.**
If it’s not in Bronze, it didn’t happen.
Release 1 exists to make Bronze unassailable.

