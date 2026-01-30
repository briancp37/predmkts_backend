# Release 01 — Bronze Level

## Overview

Release 01 establishes a production-grade Bronze data layer for prediction market data ingestion. It covers two platforms (Polymarket and Kalshi), seven entity types, and a complete CLI-driven pipeline that writes immutable, append-only JSONL.gz files to S3 with manifest-based auditability.

The Bronze layer is designed to be correct, replayable, and operationally autonomous via AWS EventBridge + ECS/Fargate scheduling — no always-on services, no manual intervention.

## Platforms & Entities

| Platform | Entity | Source | Ingestion Model | Cadence |
|---|---|---|---|---|
| Polymarket | `trades` | CLOB API | Date-scoped, cursor-based | Every 5 min |
| Polymarket | `markets` | Gamma API | Full catalog fetch | Every 1–6 hrs |
| Polymarket | `events` | Gamma API | Full catalog fetch | Every 1–6 hrs |
| Polymarket | `order_filled` | Goldsky subgraph | Date-scoped, incremental | Every 5 min |
| Kalshi | `trades` | REST API (RSA auth) | Date-scoped, cursor-based | Every 5 min |
| Kalshi | `markets` | REST API | Date-scoped | Every 1–6 hrs |
| Kalshi | `events` | REST API | Date-scoped | Every 1–6 hrs |

## S3 Storage Contract

```
s3://<BRONZE_BUCKET>/bronze/<platform>/<entity>/dt=YYYY-MM-DD/run_id=<uuid>/
  ├── part-000.jsonl.gz
  └── manifest.json
```

- **Append-only, immutable** — no overwrites, no mutations
- Every run generates a unique `run_id` (UUID4)
- Every run writes a `manifest.json` with row counts, source metadata, and file references
- Retries create new run_ids; deduplication is deferred to Silver

## CLI Commands

### Ingestion

```bash
prediction-data ingest polymarket-trades --dt YYYY-MM-DD
prediction-data ingest polymarket-markets --dt YYYY-MM-DD
prediction-data ingest polymarket-events --dt YYYY-MM-DD
prediction-data ingest polymarket-order-filled --dt YYYY-MM-DD
prediction-data ingest kalshi-trades --dt YYYY-MM-DD
prediction-data ingest kalshi-markets --dt YYYY-MM-DD
prediction-data ingest kalshi-events --dt YYYY-MM-DD
```

### Backfill

```bash
# Date range backfill (all or filtered by platform/entity)
prediction-data backfill run --start-date 2024-01-01 --end-date 2024-01-31 \
    [--platform polymarket] [--entity trades] [--dry-run]

# Auto-detect latest data and catch up to present
prediction-data backfill catchup [--platform] [--entity] [--dry-run]
```

### Monitoring & Status

```bash
prediction-data status coverage --start-date ... --end-date ... [--platform] [--entity]
prediction-data status latest [--platform] [--entity]
prediction-data status runs [--platform] [--entity] [--dt] [--last N]
prediction-data status show-run <run_id>
prediction-data status validate --start-date ... --end-date ... [--platform] [--entity]
```

## Architecture

```
EventBridge Schedule → ECS Task (Fargate) → prediction-data CLI → S3 Bronze + CloudWatch Logs
```

Each run is stateless, short-lived, and self-contained. Backfills use the same ECS task definitions with CLI argument overrides.

## Sprint Breakdown

| # | Sprint | Status | Description |
|---|---|---|---|
| 01 | Project Bootstrap | Complete | Python project setup, CLI skeleton, structured logging |
| 02 | Core Infrastructure | Complete | HTTP client with retries, S3 storage layer, manifest schema, run_id management |
| 03 | Polymarket Integration | Complete | Gamma + Data API clients, trades/markets/events ingestion |
| 04 | Kalshi Integration | Complete | RSA auth, cursor pagination, trades/markets/events ingestion |
| 05 | AWS Infrastructure | Complete | CloudFormation templates: S3, IAM, ECS, EventBridge, CloudWatch |
| 06 | Validation & Delivery | In Progress | E2E tests pass; awaiting live AWS scheduled run validation (24hr+) |
| 07 | Historical Backfill | Complete | CLOB API client, `backfill run` CLI with date range support |
| 08 | Order Filled Ingestion | Complete | Goldsky subgraph client, parquet-to-bronze converter |
| 09 | Monitoring & Status | Complete | `status` command suite: coverage, runs, show-run, validate |
| 10 | Incremental Catchup | Complete | Incremental timestamp-based fetching, `backfill catchup` command |

### Completion Summary

- **9 of 10 sprints complete**
- **55 of 57 categories passing**
- **433+ unit tests, 31+ integration tests**
- **Remaining:** Sprint 06 blocked on live AWS infrastructure validation (scheduled_run_validation, final_deployment)

## Key Design Decisions

- **Cursor-based pagination** for trades (CLOB API) — no record limit, supports full historical backfill
- **Incremental ingestion** for `order_filled` — fetches only records newer than the last known timestamp rather than re-fetching entire days
- **S3 delimiter listing** for discovery — fast partition enumeration without full key scans
- **Parquet-to-bronze converter** for historical `order_filled` data — streams 15 GB / 313M row parquet file via row groups, resolves float-precision asset IDs against markets catalog
- **No Silver/Gold assumptions** in Bronze code — clean layer separation for future releases

## Non-Goals (Deferred to Release 02+)

- Iceberg / Silver transforms
- ClickHouse / Gold loaders
- Canonical IDs and deduplication
- Schema enforcement beyond write-safety
- Analytics, dashboards, or pipeline UIs
- Dagster or similar orchestration frameworks
