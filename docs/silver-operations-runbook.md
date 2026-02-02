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

## Quality Check Configuration

Quality checks run automatically during Silver processing and enforce data integrity before any records are written to Iceberg. Checks use **fail-fast semantics**: the first failure aborts processing for that manifest (other days continue).

### Check Types

| Check | What it validates | Failure behavior |
|-------|------------------|-----------------|
| **non_null** | Required columns are not null | Hard fail |
| **uniqueness** | Primary key column has no duplicates in batch | Hard fail |
| **timestamp_range** | `event_ts` within partition date ± 1 day, not in future | Hard fail |
| **referential** | Trade `platform_market_id` exists in known markets | Warn only (logs warning, does not fail) |

Checks run in this order: non_null → uniqueness → timestamp_range → referential.

### Per-Entity Configuration

Configuration is defined in `src/prediction_data/silver/quality.py`.

**Non-null required columns:**

| Entity | Required columns |
|--------|-----------------|
| `polymarket/trades` | `event_ts`, `platform_trade_id`, `platform_market_id`, `maker`, `taker`, `price`, `usd_amount`, `token_amount` |
| `polymarket/markets` | `event_ts`, `platform_market_id` |
| `polymarket/events` | `event_ts`, `platform_event_id` |
| `kalshi/trades` | `event_ts`, `platform_trade_id`, `platform_market_id` |
| `kalshi/markets` | `event_ts`, `platform_market_id` |
| `kalshi/events` | `event_ts`, `platform_event_id` |

**Uniqueness key column:**

| Entity | Key column |
|--------|-----------|
| `*/trades` | `platform_trade_id` |
| `*/markets` | `platform_market_id` |
| `*/events` | `platform_event_id` |

**Timestamp range:** All entities use the partition date as `expected_date` with a tolerance of ±1 day.

**Referential check:** Only applies to trades entities. Validates `platform_market_id` against known Silver market IDs. Runs in warn-only mode — orphan trades are logged but not rejected.

### Skipping Quality Checks

Use `--skip-quality-checks` to bypass all checks for a processing run:

```bash
prediction-data silver process --platform polymarket --entity trades \
    --dt 2024-06-15 --skip-quality-checks
```

Use this sparingly — it allows malformed data into Silver tables.

### Reading Quality Check Failures

On failure, the error log includes:
- **check_name**: Which check failed (e.g., `non_null`, `uniqueness`)
- **failed_count**: Number of records that failed
- **error_message**: Description of the failure
- **sample_failures**: Up to 5 example failing records with row indices

Example failure output:
```
Quality check 'non_null' failed: 3 failures. Non-null violation in columns: ['event_ts', 'platform_trade_id']
```

Search structured logs for `quality_check_failed` to find all failures, or `quality_check_result` for both passes and failures.

### Extending Quality Checks

To add a custom check, subclass `QualityCheck` in `src/prediction_data/silver/quality.py`:

```python
class MyCustomCheck(QualityCheck):
    @property
    def name(self) -> str:
        return "my_custom_check"

    def run(self, records: list[dict[str, Any]]) -> QualityCheckResult:
        # validate records, return QualityCheckResult
        ...
```

Then add it to the `checks_for_entity()` function to include it in the pipeline.

## Environment Requirements

| Variable | Required | Description |
|----------|----------|-------------|
| `BRONZE_BUCKET` | Yes | S3 bucket for Bronze and Silver data |
| `AWS_REGION` | No | AWS region (default: us-east-1) |

AWS credentials must have access to: S3 (read/write), Glue Catalog (CRUD on `prediction_silver` database).
