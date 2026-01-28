# Operations Runbook

Operational procedures for the Bronze-level prediction data ingestion pipeline.

## Quick Reference

| Job | Command | Schedule | Log Group |
|-----|---------|----------|-----------|
| Polymarket Trades | `prediction-data ingest polymarket-trades --dt {date}` | Every 5 min | `/ecs/prediction-data-{env}` |
| Polymarket Markets | `prediction-data ingest polymarket-markets --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |
| Polymarket Events | `prediction-data ingest polymarket-events --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |
| Kalshi Trades | `prediction-data ingest kalshi-trades --dt {date}` | Every 5 min | `/ecs/prediction-data-{env}` |
| Kalshi Markets | `prediction-data ingest kalshi-markets --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |
| Kalshi Events | `prediction-data ingest kalshi-events --dt {date}` | Every 1 hr | `/ecs/prediction-data-{env}` |

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
