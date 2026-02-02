# Silver Layer Operations Runbook

## Overview

The Silver layer normalizes Bronze JSONL data into Iceberg tables (Glue Catalog, Parquet/ZSTD, day-partitioned). All operations are driven by Bronze manifests and tracked for idempotency.

**Tables:** `prediction_silver` database in AWS Glue Catalog.
Valid targets: `polymarket/trades`, `polymarket/markets`, `polymarket/events`, `kalshi/trades`, `kalshi/markets`, `kalshi/events`.

## Daily Operations

### Processing New Data

```bash
# Process a single day
prediction-data silver process --platform polymarket --entity trades --dt 2024-06-15

# Process a date range
prediction-data silver process --platform polymarket --entity trades \
    --start-date 2024-06-01 --end-date 2024-06-30

# Preview without writing
prediction-data silver process --platform polymarket --entity trades --dt 2024-06-15 --dry-run
```

The processor discovers Bronze manifests, deduplicates records, normalizes to Silver schema, runs quality checks, and upserts into Iceberg tables. Each manifest is tracked in an S3 state file so re-runs skip already-processed data.

### Scheduled Maintenance

```bash
# Daily: compact small files
prediction-data silver maintain --op compact

# Weekly: expire old snapshots + remove orphaned files
prediction-data silver maintain --op expire --op orphans

# All operations at once
prediction-data silver maintain

# Preview any maintenance operation
prediction-data silver maintain --dry-run
```

| Operation | What it does | Default threshold |
|-----------|-------------|-------------------|
| `compact` | Merges small files (>50 files, <64MB each) into ~256MB targets | — |
| `expire` | Removes old Iceberg snapshots | 7 days |
| `orphans` | Deletes .parquet files not referenced by any snapshot | 7 days |

Target a specific table or partition:

```bash
prediction-data silver compact --table polymarket/trades --partition 2024-06-15
prediction-data silver expire-snapshots --table polymarket/trades --older-than-days 14
prediction-data silver remove-orphans --table polymarket/trades
```

## Backfills

### Backfilling Silver from Existing Bronze Data

```bash
# Backfill a range (skips already-processed manifests)
prediction-data silver process --platform polymarket --entity trades \
    --start-date 2024-01-01 --end-date 2024-06-30

# Force reprocess (ignores idempotency state)
prediction-data silver process --platform polymarket --entity trades \
    --start-date 2024-01-01 --end-date 2024-01-31 --force-reprocess
```

Processing is sequential by day. If a day fails, the pipeline continues to the next day and prints a failure summary at the end.

### Rebuilding a Partition

To fully rebuild a Silver partition from Bronze:

```bash
prediction-data silver process --platform polymarket --entity trades \
    --dt 2024-06-15 --force-reprocess
```

The `--force-reprocess` flag bypasses the state check. Because Silver uses upsert (not append), reprocessing is safe and produces the same result.

## Troubleshooting

### Common Issues

**"No manifests found"**
- Verify Bronze data exists: check `s3://{bucket}/bronze/{platform}/{entity}/dt={date}/` for `_manifest.json` files.
- Confirm the `BRONZE_BUCKET` environment variable is set correctly.

**Quality check failures**
- The pipeline fails fast on the first quality check failure. The error message includes the check name and sample failing records.
- To bypass temporarily: `--skip-quality-checks` (use with caution).
- Common causes: null required fields, duplicate primary keys in source data, timestamps outside expected range (±1 day from partition date).

**"Already processed" (no output)**
- The manifest was already processed. Use `--force-reprocess` to override.
- State is stored at: `s3://{bucket}/silver/_state/{platform}/{entity}/processed.jsonl`

**Maintenance errors**
- Each table's maintenance runs independently. A failure on one table does not block others.
- Errors are collected and printed in a summary at the end.
- Compaction requires >50 small files to trigger; "skipped" means the threshold was not met.

### Inspecting State

The processed-manifest state file is an append-only JSONL log:

```
s3://{bucket}/silver/_state/{platform}/{entity}/processed.jsonl
```

Each line records: `run_id`, `platform`, `entity`, `dt`, `processed_at`. Download and inspect with:

```bash
aws s3 cp s3://$BRONZE_BUCKET/silver/_state/polymarket/trades/processed.jsonl - | tail -20
```

### Late-Arriving Data

Records older than 7 days relative to the partition date are flagged as late-arriving. This generates a warning log but does **not** fail the pipeline. The records are still written to Silver.

Search logs for `late_arriving_data` to find instances.

### Catalog Entity Processing (Markets/Events)

For catalog entities, the processor applies **snapshot-supersedes-deltas** logic:
- A full snapshot manifest for a given day supersedes all earlier delta manifests for that day.
- Delta manifests generated after the latest snapshot are processed in order.
- This ensures correct state reconstruction when both snapshot and incremental ingestion have run.

## Table Initialization

Run once to create all Silver tables in Glue Catalog:

```bash
prediction-data silver init-tables
prediction-data silver init-tables --dry-run  # preview
```

All tables are partitioned by `days(event_ts)`, sorted by `(primary_key, event_ts)`, and use Parquet with ZSTD compression (format version 2).

## Environment Requirements

| Variable | Required | Description |
|----------|----------|-------------|
| `BRONZE_BUCKET` | Yes | S3 bucket for Bronze and Silver data |
| `AWS_REGION` | No | AWS region (default: us-east-1) |

AWS credentials must have access to: S3 (read/write), Glue Catalog (CRUD on `prediction_silver` database).
