# Prediction Data

Data pipeline for prediction market data ingestion and processing. Ingests trades and markets from Polymarket and Kalshi into an S3 Bronze layer using scheduled ECS Fargate tasks.

## Quick Start

```bash
# 1. Verify local setup
python scripts/check_setup.py

# 2. Run an ingestion locally
prediction-data ingest polymarket-trades --dt 2024-01-28
prediction-data ingest kalshi-markets --dt 2024-01-28
```

## Architecture

- **Sources:** Polymarket (Data API, Gamma API), Kalshi (Trade API v2 with RSA auth)
- **Compute:** ECS Fargate tasks triggered by EventBridge Scheduler
- **Storage:** S3 Bronze bucket (`bronze/{platform}/{entity}/dt={date}/run_id={uuid}/`)
- **Monitoring:** CloudWatch logs, metric filters, alarms, and dashboard
- **Idempotency:** Each run gets a unique UUID — no overwrites, safe to retry

## Key Commands

| Command | Description |
|---------|-------------|
| `prediction-data ingest polymarket-trades --dt DATE` | Ingest Polymarket trades |
| `prediction-data ingest polymarket-markets --dt DATE` | Ingest Polymarket markets |
| `prediction-data ingest kalshi-trades --dt DATE` | Ingest Kalshi trades |
| `prediction-data ingest kalshi-markets --dt DATE` | Ingest Kalshi markets |

## Documentation

- [OPERATIONS.md](OPERATIONS.md) — Operational runbook (backfills, troubleshooting, monitoring)
- [infrastructure/README.md](infrastructure/README.md) — AWS deployment guide
- [CLAUD.md](CLAUD.md) — AI context and API reference
