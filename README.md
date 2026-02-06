# Prediction Data

Data pipeline for prediction market data ingestion and processing. Ingests trades, markets, and events from Polymarket and Kalshi into an S3 Bronze layer using scheduled ECS Fargate tasks.

## Quick Start

```bash
# 1. Verify local setup
python scripts/check_setup.py

# 2. Run an ingestion locally
prediction-data ingest polymarket-order-filled --dt 2024-01-28
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
| `prediction-data ingest polymarket-order-filled --dt DATE` | Ingest Polymarket order_filled events |
| `prediction-data ingest polymarket-markets --dt DATE` | Ingest Polymarket markets |
| `prediction-data ingest polymarket-events --dt DATE` | Ingest Polymarket events |
| `prediction-data ingest kalshi-trades --dt DATE` | Ingest Kalshi trades |
| `prediction-data ingest kalshi-markets --dt DATE` | Ingest Kalshi markets |
| `prediction-data ingest kalshi-events --dt DATE` | Ingest Kalshi events |

## Pipeline Diagnostics

Diagnose data pipeline issues across all layers (Bronze → Silver → Gold → API):

```bash
# Run full markets diagnostics
python scripts/diagnose_markets.py
```

The script checks:
- **External API** — Polymarket Gamma API connectivity
- **Bronze Layer** — S3 manifests and ingestion freshness
- **Silver Layer** — Iceberg table snapshots and row counts
- **Gold Layer** — ClickHouse dimension tables (dim_market, dim_outcome, etc.)
- **REST API** — Endpoint responses and data completeness
- **Infrastructure** — EventBridge schedule status

Outputs color-coded status, natural language explanations, and recommended fixes.

## Documentation

- [OPERATIONS.md](OPERATIONS.md) — Operational runbook (backfills, troubleshooting, monitoring)
- [infrastructure/README.md](infrastructure/README.md) — AWS deployment guide
- [CLAUDE.md](CLAUDE.md) — AI context and API reference
