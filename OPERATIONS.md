# Operations Runbook

Operational procedures for the prediction data pipeline (Bronze ingestion and Silver processing).

## Quick Reference

### Bronze Ingestion Jobs

| Job | Command | Schedule | Log Group |
|-----|---------|----------|-----------|
| Polymarket Trades | `prediction-data ingest polymarket-trades --dt {date}` | Every 5 min | `/ecs/prediction-data-{env}` |
| Polymarket Markets | `prediction-data ingest polymarket-markets --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |
| Polymarket Events | `prediction-data ingest polymarket-events --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |
| Kalshi Trades | `prediction-data ingest kalshi-trades --dt {date}` | Every 5 min | `/ecs/prediction-data-{env}` |
| Kalshi Markets | `prediction-data ingest kalshi-markets --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |
| Kalshi Events | `prediction-data ingest kalshi-events --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |
| Polymarket Order Filled | `prediction-data backfill catchup --platform polymarket --entity order_filled` | Every 15 min | `/ecs/prediction-data-{env}` |

### Silver Processing Jobs

| Job | Command | Schedule | Log Group |
|-----|---------|----------|-----------|
| Silver Trades (end-of-day) | `prediction-data silver process --platform polymarket --entity trades --start-date {7d_ago} --end-date {today} --closed-days-only` | Daily 06:00 UTC | `/ecs/prediction-data-{env}` |
| Silver Order Filled (end-of-day) | `prediction-data silver process --platform polymarket --entity order_filled --start-date {7d_ago} --end-date {today} --closed-days-only` | Daily 06:00 UTC | `/ecs/prediction-data-{env}` |
| Silver Markets (same-day) | `prediction-data silver process --platform polymarket --entity markets --dt {today}` | Daily 07:00 UTC | `/ecs/prediction-data-{env}` |
| Silver Events (same-day) | `prediction-data silver process --platform polymarket --entity events --dt {today}` | Daily 07:00 UTC | `/ecs/prediction-data-{env}` |
| Kalshi Silver Trades | `prediction-data silver process --platform kalshi --entity trades --start-date {7d_ago} --end-date {today} --closed-days-only` | Daily 06:00 UTC | `/ecs/prediction-data-{env}` |
| Kalshi Silver Markets | `prediction-data silver process --platform kalshi --entity markets --dt {today}` | Daily 07:00 UTC | `/ecs/prediction-data-{env}` |
| Kalshi Silver Events | `prediction-data silver process --platform kalshi --entity events --dt {today}` | Daily 07:00 UTC | `/ecs/prediction-data-{env}` |
| Silver Maintenance (compact) | `prediction-data silver maintain --op compact` | Daily 08:00 UTC | `/ecs/prediction-data-{env}` |
| Silver Maintenance (full) | `prediction-data silver maintain` | Weekly Sun 08:00 UTC | `/ecs/prediction-data-{env}` |

## Polymarket Order Filled Ingestion

The `order_filled` entity uses the Goldsky GraphQL subgraph to fetch OrderFilledEvents. Due to the high volume (~313M historical records), it uses streaming batch uploads to S3 rather than accumulating everything in memory.

### Running Order Filled Ingestion

```bash
# Incremental catchup (recommended) - fetches only new records since last run
prediction-data backfill catchup --platform polymarket --entity order_filled

# Single date ingestion
prediction-data ingest polymarket-order-filled --dt 2024-06-15

# Date range backfill
prediction-data backfill run --platform polymarket --entity order_filled \
    --start-date 2024-06-01 --end-date 2024-06-30

# Dry run (preview without writing)
prediction-data backfill run --platform polymarket --entity order_filled \
    --start-date 2024-06-01 --end-date 2024-06-30 --dry-run
```

### Batch Flushing

Records are fetched from Goldsky in pages of 1,000 and accumulated in memory. Every **500,000 records**, a batch is:
1. Uploaded to S3 as a gzip-compressed JSONL part file
2. An intermediate manifest is written (for crash recovery)
3. Memory is freed

This means you'll see progress logs every ~500 pages (500k records / 1k per page).

### Monitoring Progress

Progress is logged after each batch flush:

```bash
# Tail logs in real-time
aws logs tail /ecs/prediction-data-dev --follow

# Or locally (logs to stdout with structlog)
prediction-data backfill catchup --platform polymarket --entity order_filled
```

**Key log messages to watch:**

| Log Message | Meaning |
|-------------|---------|
| `Starting Goldsky order filled batched fetch` | Ingestion started |
| `Goldsky order filled pagination progress` | Fetching pages (every page) |
| `Flushed order_filled batch to S3` | Batch uploaded (every 500k records) |
| `Order_filled ingestion complete` | All done |

Example progress log:
```
Flushed order_filled batch to S3  part=1 batch_rows=500000 total_rows=500000 latest_timestamp=1706745623
Flushed order_filled batch to S3  part=2 batch_rows=500000 total_rows=1000000 latest_timestamp=1706832045
```

### Crash Recovery

If the process crashes mid-run, the intermediate manifest tracks progress. The next `catchup` run will:
1. Find the last manifest's `latest_timestamp`
2. Resume fetching from that timestamp
3. No duplicate records (Goldsky uses `timestamp_gte` filter)

### Historical Backfill from Parquet

For bulk historical data (pre-2024), use the parquet conversion script instead of hitting Goldsky:

```bash
# Convert from the monolithic order_filled.parquet (~15 GB, 313M rows)
python scripts/backfill_order_filled_from_parquet.py \
    --start-date 2022-11-01 --end-date 2024-01-01

# Dry run
python scripts/backfill_order_filled_from_parquet.py \
    --start-date 2024-01-01 --end-date 2024-03-31 --dry-run
```

This streams the parquet file once and buckets by date, flushing completed days as it goes.

## Silver Processing

### Production Cadence by Entity Type

Entity types have different processing models based on their data characteristics:

**Stream entities (trades, order_filled):**
- Bronze ingestion runs continuously (every 5-15 min), producing independent manifests per run.
- Silver processing uses **end-of-day batch model**: each morning, process yesterday's complete data.
- Use `--closed-days-only` to prevent processing today's incomplete partition.
- The 7-day lookback window (`--start-date {7d_ago}`) catches any days missed due to failures.
- Already-processed manifests are skipped via the Silver state store (idempotent).

**Catalog entities (markets, events):**
- Bronze ingestion runs daily (full snapshot or incremental delta).
- Silver processing runs **same-day** after ingestion completes — catalog snapshots are complete upon ingestion.
- No `--closed-days-only` needed since the snapshot is self-contained.

### Running Silver Processing

```bash
# End-of-day processing for stream entities (trades, order_filled)
# Processes only completed days — safe for cron
prediction-data silver process \
    --platform polymarket --entity trades \
    --start-date 2026-01-27 --end-date 2026-02-03 \
    --closed-days-only

# Same-day processing for catalog entities (markets, events)
# Process today's snapshot immediately after ingestion
prediction-data silver process \
    --platform polymarket --entity markets \
    --dt 2026-02-03

# Dry run to preview what would be processed
prediction-data silver process \
    --platform polymarket --entity trades \
    --start-date 2026-01-27 --end-date 2026-02-03 \
    --closed-days-only --dry-run

# Force reprocess (ignore state store)
prediction-data silver process \
    --platform polymarket --entity trades \
    --dt 2026-02-02 --force-reprocess
```

### EventBridge Cron Schedules

Example cron expressions for AWS EventBridge Scheduler:

```
# Stream entities: end-of-day processing at 06:00 UTC daily
cron(0 6 * * ? *)

# Catalog entities: same-day processing at 07:00 UTC daily (after ingestion)
cron(0 7 * * ? *)

# Silver maintenance (compact): daily at 08:00 UTC
cron(0 8 * * ? *)

# Silver maintenance (full — compact + expire + orphans): weekly Sunday 08:00 UTC
cron(0 8 ? * SUN *)
```

### Future: Near-Real-Time Silver

The current model processes stream entities as end-of-day batches. The architecture
already supports near-real-time processing because each Bronze catchup cycle produces
an independent `run_id` and manifest. To enable near-real-time Silver:

1. Run `silver process` more frequently (e.g., every 30 min) without `--closed-days-only`.
2. Each invocation discovers new unprocessed manifests and appends to Silver.
3. Deduplication is handled by Iceberg merge/upsert with merge keys.
4. Trade-off: more frequent processing means more small files, requiring more
   frequent compaction.

This is a scheduling change, not a code change. The continuous ingestion architecture
(independent run_ids, per-manifest state tracking, Iceberg upsert dedup) already
supports it.

## Checking Run Status

### View Recent Logs

```bash
# Tail live logs
aws logs tail /ecs/prediction-data-dev --follow

# View last hour of logs
aws logs tail /ecs/prediction-data-dev --since 1h
```

### Search for a Specific Run

```bash
# Find a run by run_id
aws logs filter-log-events \
  --log-group-name /ecs/prediction-data-dev \
  --filter-pattern '"run_id" "a1b2c3d4-e5f6-7890-abcd-ef1234567890"'

# Find all completed runs in last hour
aws logs filter-log-events \
  --log-group-name /ecs/prediction-data-dev \
  --start-time $(($(date +%s) - 3600))000 \
  --filter-pattern '"Run completed"'

# Find all errors in last hour
aws logs filter-log-events \
  --log-group-name /ecs/prediction-data-dev \
  --start-time $(($(date +%s) - 3600))000 \
  --filter-pattern '"ERROR"'
```

### CloudWatch Insights Queries

```sql
-- Recent run summary
fields @timestamp, run_id, platform, entity, event
| filter event in ["Run started", "Run completed"]
| sort @timestamp desc
| limit 50

-- Average run duration by job type
fields @timestamp, run_id, platform, entity, duration_seconds
| filter event = "Run completed"
| stats count() as runs, avg(duration_seconds) as avg_duration by platform, entity
```

### Check ECS Task Status

```bash
# List running tasks
aws ecs list-tasks --cluster prediction-data-dev --desired-status RUNNING

# List recently stopped tasks
aws ecs list-tasks --cluster prediction-data-dev --desired-status STOPPED

# Get details on a specific task
aws ecs describe-tasks \
  --cluster prediction-data-dev \
  --tasks <task-arn>
```

### CloudWatch Dashboard

Open in the AWS Console:
```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=prediction-data-{env}
```

## Manual Backfills

Each backfill run generates a unique `run_id`, so re-running the same date creates a new partition in S3 without overwriting existing data.

### Local Backfill

```bash
# Single date
prediction-data ingest polymarket-trades --dt 2024-01-15
prediction-data ingest polymarket-markets --dt 2024-01-15
prediction-data ingest polymarket-events --dt 2024-01-15
prediction-data ingest kalshi-trades --dt 2024-01-15
prediction-data ingest kalshi-markets --dt 2024-01-15
prediction-data ingest kalshi-events --dt 2024-01-15

# Date range (parallel)
for dt in 2024-01-{01..31}; do
  prediction-data ingest polymarket-trades --dt $dt &
done
wait
```

### ECS Backfill (Production)

Run a one-off ECS task with a custom command override:

```bash
ENV=dev
CLUSTER=prediction-data-$ENV
TASK_DEF=prediction-data-ingest-$ENV
SUBNETS=<your-subnet-ids>
SG=<your-security-group-id>

aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $TASK_DEF \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "prediction-data",
      "command": ["ingest", "polymarket-trades", "--dt", "2024-01-15"]
    }]
  }'
```

### Verify Backfill Output

```bash
# List objects for a specific date
aws s3 ls s3://prediction-bronze-dev/bronze/polymarket/trades/dt=2024-01-15/ --recursive

# Download and inspect a manifest
aws s3 cp s3://prediction-bronze-dev/bronze/polymarket/trades/dt=2024-01-15/run_id=<uuid>/manifest.json -
```

## Troubleshooting Common Failures

### API Timeout or Connection Error

**Symptoms:** Logs show `httpx.ConnectTimeout` or `httpx.ReadTimeout`.

**Resolution:** The pipeline has built-in retry logic (3 retries with exponential backoff, max 60s delay). If retries are exhausted:
1. Check external API status (Polymarket or Kalshi)
2. Re-run the failed job manually — a new `run_id` is generated, no data corruption risk

### Rate Limiting (HTTP 429)

**Symptoms:** Logs show `429 Too Many Requests`.

**Resolution:** The HTTP client retries on 429 automatically. If persistent:
1. Review Kalshi rate limits (Basic tier: 20 reads/sec)
2. Reduce concurrency if running parallel backfills
3. Add delays between parallel runs

### ECS Task Exits with Non-Zero Code

**Symptoms:** CloudWatch alarm fires, ECS task shows `STOPPED` with non-zero exit code.

**Resolution:**
1. Check CloudWatch logs for the task: `aws logs tail /ecs/prediction-data-dev --since 30m`
2. Look for the error message and stack trace
3. Common causes: invalid credentials, S3 permission denied, API changes
4. Re-run after fixing — each run gets a new `run_id`

### Missing Scheduled Runs

**Symptoms:** CloudWatch alarm `MissingTradesRun` or `MissingMarketsRun` fires.

**Resolution:**
1. Check EventBridge schedule is enabled:
   ```bash
   aws scheduler list-schedules --group-name prediction-data-dev
   ```
2. Check ECS task failures in the cluster
3. Verify the ECS task definition still references a valid ECR image
4. Check IAM role permissions haven't changed

### S3 Permission Denied

**Symptoms:** Logs show `botocore.exceptions.ClientError: AccessDenied`.

**Resolution:**
1. Verify the ECS task role has S3 permissions:
   ```bash
   aws iam get-role-policy --role-name prediction-data-task-dev --policy-name TaskPolicy
   ```
2. Verify the bucket name matches `BRONZE_BUCKET` environment variable
3. Check the S3 bucket policy hasn't been modified

## AWS Resource Inventory

All resources are parameterized by environment (`dev`, `staging`, `prod`).

| Resource | Name Pattern | CloudFormation Stack |
|----------|-------------|---------------------|
| S3 Bucket | `prediction-bronze-{env}` | `prediction-bronze-bucket` |
| ECS Cluster | `prediction-data-{env}` | `prediction-data-ecs` |
| Task Definition | `prediction-data-ingest-{env}` | `prediction-data-ecs` |
| Log Group | `/ecs/prediction-data-{env}` | `prediction-data-ecs` |
| SNS Topic | `prediction-data-alerts-{env}` | `prediction-data-monitoring` |
| Dashboard | `prediction-data-{env}` | `prediction-data-monitoring` |
| Schedule Group | `prediction-data-{env}` | `prediction-data-schedules` |
| IAM Execution Role | `prediction-data-execution-{env}` | `prediction-data-iam-roles` |
| IAM Task Role | `prediction-data-task-{env}` | `prediction-data-iam-roles` |
| ECR Repository | `prediction-data` | Manual |

## S3 Data Layout

```
s3://prediction-bronze-{env}/
  bronze/
    {platform}/          # polymarket | kalshi
      {entity}/          # trades | markets | events
        dt={YYYY-MM-DD}/
          run_id={uuid}/
            part-000.jsonl.gz
            manifest.json
```

Each run produces a unique `run_id` directory. Multiple runs for the same date coexist without conflict.
