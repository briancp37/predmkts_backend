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

### Silver Processing Jobs (Near-Continuous via EventBridge)

Silver processing uses a near-continuous model via EventBridge Scheduler (`eventbridge-silver-schedules.yaml`). The `silver catchup` command auto-detects new Bronze manifests and processes them incrementally, with per-entity concurrency guards to prevent overlapping runs.

| Job | Command | Schedule | Log Group |
|-----|---------|----------|-----------|
| Polymarket Trades | `prediction-data silver catchup --platform polymarket --entity trades --skip-if-concurrent` | Every 10 min | `/ecs/prediction-data-{env}` |
| Polymarket Markets | `prediction-data silver catchup --platform polymarket --entity markets --skip-if-concurrent` | Every 30 min | `/ecs/prediction-data-{env}` |
| Polymarket Events | `prediction-data silver catchup --platform polymarket --entity events --skip-if-concurrent` | Every 30 min | `/ecs/prediction-data-{env}` |
| Kalshi Trades | `prediction-data silver catchup --platform kalshi --entity trades --skip-if-concurrent` | Every 10 min (DISABLED) | `/ecs/prediction-data-{env}` |
| Kalshi Markets | `prediction-data silver catchup --platform kalshi --entity markets --skip-if-concurrent` | Every 30 min (DISABLED) | `/ecs/prediction-data-{env}` |
| Kalshi Events | `prediction-data silver catchup --platform kalshi --entity events --skip-if-concurrent` | Every 30 min (DISABLED) | `/ecs/prediction-data-{env}` |
| Silver Maintenance (compact) | `prediction-data silver maintain --op compact --skip-if-concurrent` | Daily 04:00 UTC | `/ecs/prediction-data-{env}` |
| Silver Maintenance (full) | `prediction-data silver maintain --skip-if-concurrent` | Weekly Sun 04:00 UTC | `/ecs/prediction-data-{env}` |

### Gold Processing Jobs

| Job | Command | Schedule | Log Group |
|-----|---------|----------|-----------|
| Gold Daily Run | `prediction-data gold daily-run` | Daily 00:00 UTC | `/ecs/prediction-data-{env}` |
| Gold CH Load | `prediction-data gold ch-load --all --lookback-days 90` | Daily 00:30 UTC | `/ecs/prediction-data-{env}` |
| Gold Freshness Check | `prediction-data gold freshness` | Daily 01:00 UTC | `/ecs/prediction-data-{env}` |

**Gold scheduling logic:**
- 00:00 UTC: `gold daily-run` executes 4 steps in order: load-dims, process-trades, compute-marks, compute-wallet-metrics. Fail-forward by default (logs errors, continues to next step).
- 00:30 UTC: `gold ch-load --all` reads S3 Gold Parquet within 90-day lookback window and inserts into ClickHouse. ReplacingMergeTree handles deduplication; TTL handles expiry.
- 01:00 UTC: `gold freshness` verifies all Gold datasets are fresh and within SLA. Reports stale/broken datasets.

**ECS task definition overrides for Gold commands:**

Gold commands reuse the same ECS task definition as Bronze/Silver. Override the container command via EventBridge or manual `aws ecs run-task`:

```bash
# Manual Gold daily-run via ECS
aws ecs run-task \
  --cluster prediction-data-$ENV \
  --task-definition prediction-data-ingest-$ENV \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "prediction-data",
      "command": ["gold", "daily-run"]
    }]
  }'

# Manual CH load for a specific table
aws ecs run-task \
  --cluster prediction-data-$ENV \
  --task-definition prediction-data-ingest-$ENV \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "prediction-data",
      "command": ["gold", "ch-load", "--table", "market_mark_daily", "--lookback-days", "90"]
    }]
  }'

# Manual rebuild for a date range
aws ecs run-task \
  --cluster prediction-data-$ENV \
  --task-definition prediction-data-ingest-$ENV \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "prediction-data",
      "command": ["gold", "rebuild", "--table", "market_mark_daily", "--start-date", "2026-01-01", "--end-date", "2026-01-31", "--force"]
    }]
  }'
```

**Wrapper script for cron execution:**

```bash
# Run the full Gold daily pipeline locally or from cron
./scripts/gold_daily_cron.sh

# With options
./scripts/gold_daily_cron.sh --dt 2026-02-01 --lookback-days 30
./scripts/gold_daily_cron.sh --dry-run
```

**EventBridge cron schedules (Gold):**

```
# Gold daily-run: midnight UTC (after Silver processing completes)
cron(0 0 * * ? *)

# Gold CH load: 00:30 UTC (after daily-run writes S3 Gold)
cron(30 0 * * ? *)

# Gold freshness check: 01:00 UTC (verify all datasets fresh)
cron(0 1 * * ? *)
```

Deploy Gold schedules via CloudFormation:
```bash
aws cloudformation deploy \
  --template-file infrastructure/eventbridge-gold-schedules.yaml \
  --stack-name prediction-data-gold-schedules \
  --parameter-overrides \
    Environment=$ENV \
    ECSClusterArn=$CLUSTER_ARN \
    TaskDefinitionArn=$TASK_DEF_ARN \
    SubnetIds=<your-subnet-ids> \
    SecurityGroupIds=<your-security-group-id> \
  --capabilities CAPABILITY_NAMED_IAM
```

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

Silver processing uses a **near-continuous model** where `silver catchup` runs on a frequent schedule via EventBridge Scheduler. Each invocation auto-detects new Bronze manifests and processes them. The majority of invocations are no-ops (no new data) and exit within seconds.

**Stream entities (trades, order_filled):**
- Bronze ingestion runs continuously (every 5-15 min), producing independent manifests per run.
- Silver catchup runs **every 10 minutes**, discovering and processing new Bronze manifests immediately.
- Per-entity concurrency guards (`--skip-if-concurrent`) prevent overlapping runs — if the previous catchup is still processing, the new invocation exits cleanly (code 0).
- Data appears in Silver within ~15 minutes of the on-chain event.

**Catalog entities (markets, events):**
- Bronze ingestion runs hourly (full snapshot or incremental delta).
- Silver catchup runs **every 30 minutes**, processing new Bronze manifests as they appear.
- Snapshot-supersedes-deltas: a snapshot manifest supersedes earlier delta manifests for the same day.

### Running Silver Processing

```bash
# Near-continuous catchup (used by EventBridge schedules)
prediction-data silver catchup --platform polymarket --entity trades --skip-if-concurrent

# Manual catchup without concurrency guard
prediction-data silver catchup --platform polymarket --entity trades

# Catchup with explicit start date (overrides auto-detect)
prediction-data silver catchup --platform polymarket --entity trades --from-date 2026-01-15

# Dry run to preview what would be processed
prediction-data silver catchup --platform polymarket --entity trades --dry-run

# Single-date or date-range processing (for manual backfills)
prediction-data silver process \
    --platform polymarket --entity trades \
    --start-date 2026-01-27 --end-date 2026-02-03

# Force reprocess (ignore state store)
prediction-data silver process \
    --platform polymarket --entity trades \
    --dt 2026-02-02 --force-reprocess
```

### EventBridge Schedules

Silver schedules are deployed via `infrastructure/eventbridge-silver-schedules.yaml` into the `prediction-data-silver-{env}` schedule group:

```bash
# Deploy Silver schedules
aws cloudformation deploy \
  --template-file infrastructure/eventbridge-silver-schedules.yaml \
  --stack-name prediction-data-silver-schedules \
  --parameter-overrides \
    Environment=$ENV \
    ECSClusterArn=$CLUSTER_ARN \
    TaskDefinitionArn=$TASK_DEF_ARN \
    SubnetIds=<your-subnet-ids> \
    SecurityGroupIds=<your-security-group-id> \
  --capabilities CAPABILITY_NAMED_IAM

# List Silver schedules
aws scheduler list-schedules --group-name prediction-data-silver-$ENV
```

Schedule cadences (configurable via CloudFormation parameters):
- **Trades:** `rate(10 minutes)` — Bronze order_filled ingests every 5 min; data in Silver within ~15 min
- **Catalog (markets, events):** `rate(30 minutes)` — Bronze ingests hourly; 30-min catches updates within one cycle
- **Maintenance (compact):** `cron(0 4 * * ? *)` — daily at 04:00 UTC
- **Maintenance (full):** `cron(0 4 ? * SUN *)` — weekly Sunday at 04:00 UTC

All catchup schedules use `--skip-if-concurrent` to prevent overlapping runs. Concurrency is scoped per entity type (e.g., `silver-polymarket-trades`), so trades and markets can run concurrently but two trades runs cannot.

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
| Schedule Group (Bronze) | `prediction-data-{env}` | `prediction-data-schedules` |
| Schedule Group (Gold) | `prediction-data-gold-{env}` | `prediction-data-gold-schedules` |
| Schedule Group (Silver) | `prediction-data-silver-{env}` | `prediction-data-silver-schedules` |
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
