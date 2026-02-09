# CLAUDE.md

## Project Overview

Python data pipeline for ingesting prediction market data (Polymarket, Kalshi) into S3 bronze layer, normalizing it into Silver Iceberg tables (Glue Catalog, Parquet/ZSTD, day-partitioned), and computing Gold aggregations (position accounting, PnL, market marks) served via ClickHouse.

## Quick Reference

```bash
# Install
pip install -e ".[dev]"

# Run tests (excludes integration tests)
pytest -m "not integration"

# Type check / Lint
mypy src/
ruff check src/ tests/

# Local infrastructure
docker compose up -d
docker compose down

# CLI entry point
prediction-data --help

# Start API + Frontend
uvicorn prediction_data.api.main:app --reload  # API at :8000
cd web && npm run dev                           # Frontend at :3000
```

## API References

Detailed endpoint parameters, response schemas, and pagination in `docs/api/`:
- `docs/api/polymarket-gamma.md` — Gamma API (markets, events)
- `docs/api/polymarket-clob.md` — CLOB API (trades, auth, orders)
- `docs/api/polymarket-data.md` — Data API (trades, positions)
- `docs/api/polymarket-goldsky.md` — Goldsky subgraph (OrderFilledEvents)
- `docs/api/kalshi.md` — Full Kalshi API

**Consult these files before making claims about what API parameters are or aren't available.**

## Polymarket Rate Limits

| API | Endpoint | Rate Limit |
|---|---|---|
| CLOB | `GET /data/trades` | 500 req/10s |
| Gamma | `GET /markets` | 300 req/10s |
| Gamma | `GET /events` | 500 req/10s |
| Data | `GET /trades` | 200 req/10s |
| Goldsky | `POST /subgraphs/.../gn` | No hard limit (use page_delay) |

Full reference: https://docs.polymarket.com/quickstart/introduction/rate-limits

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BRONZE_BUCKET` | Yes | S3 bucket for bronze layer data |
| `GOLD_BUCKET` | For Gold | S3 bucket for Gold layer Parquet files |
| `CLICKHOUSE_HOST` | For Gold | ClickHouse server hostname (default: localhost) |
| `DATABASE_URL` | For API | PostgreSQL connection string |
| `JWT_SECRET_KEY` | For API | Secret for JWT signing (min 32 chars) |
| `KALSHI_API_KEY_ID` | For Kalshi | Kalshi API key ID |
| `KALSHI_PRIVATE_KEY_PATH` | For Kalshi | Path to Kalshi RSA private key |

## Release & Sprint Plans

Project work is organized under `plans/release/`. Use `/sprint_generator <release_name>` to generate sprints from a RELEASE.md.

## Docker Compose Services

| Service | Description | Port | Profile |
|---|---|---|---|
| `postgres` | PostgreSQL for user data | 5432 | (always) |
| `clickhouse` | ClickHouse for Gold layer | 8123, 9000 | (always) |
| `redis` | Distributed caching | 6379 | `cache` |
| `api` | FastAPI server | 8000 | `api` |

```bash
docker compose --profile api --profile cache up -d  # All services
```

## CLI Commands

### Backfill / Catchup
```bash
prediction-data backfill run --start-date 2024-01-01 --end-date 2024-01-31
prediction-data backfill catchup --platform polymarket --entity order_filled
prediction-data backfill catchup --dry-run
```

### Status
```bash
prediction-data status coverage --start-date 2024-01-01 --end-date 2024-01-31
prediction-data status runs --platform kalshi --last 10
```

### Silver Layer
```bash
prediction-data silver init-tables
prediction-data silver catchup --platform polymarket --entity trades
prediction-data silver process --platform polymarket --entity markets --dt 2024-06-15
prediction-data silver maintain --op compact --op dedup
```

### Gold Layer
```bash
prediction-data gold daily-run
prediction-data gold load-dims
prediction-data gold load-dims --streaming  # Memory-efficient mode for ECS
prediction-data gold process-trades --dt 2024-06-15
prediction-data gold compute-marks --dt 2024-06-15
prediction-data gold ch-load --all --lookback-days 90
prediction-data gold freshness
```

#### Gold Command Memory Usage

| Command | Mode | Recommended Memory | Notes |
|---|---|---|---|
| `gold daily-run` | streaming (default) | 4GB | Streaming dimension loaders, batched processing |
| `gold daily-run --no-streaming` | standard | 16GB+ | Loads full tables into memory, writes to S3 |
| `gold load-dims --streaming` | streaming | 4GB | Direct ClickHouse inserts, skips S3 |
| `gold load-dims` | standard | 16GB+ | Full table loads + S3 writes |
| `gold ch-load --all` | - | 2GB | Reads S3 Parquet, streams to ClickHouse |
| `gold freshness` | - | 512MB | ClickHouse queries only |
| `gold process-trades` | - | 2GB | Per-day trade processing |
| `gold compute-marks` | - | 2GB | Per-day market marks |

EventBridge schedules in `infrastructure/eventbridge-gold-schedules.yaml` use configurable CPU/memory overrides:
- `gold-daily-run`: 1 vCPU / 4GB (streaming mode)
- `gold-ch-load`: 0.5 vCPU / 2GB
- `gold-freshness-check`: 0.25 vCPU / 512MB

### Pipeline Diagnostics
```bash
python scripts/diagnose_markets.py
```

## S3 Key Structure

```
bronze/{platform}/{entity}/dt={YYYY-MM-DD}/run_id={uuid}/
  ├── part-000.json
  └── _manifest.json

gold/{table_name}/day={YYYY-MM-DD}/part-000.parquet
```

## Project Structure

```
predmkts_backend/
├── src/prediction_data/
│   ├── api/           # FastAPI REST API
│   ├── bronze/        # Bronze layer ingestion
│   ├── silver/        # Silver layer processing
│   ├── gold/          # Gold layer aggregations
│   └── core/          # Shared configuration
├── web/               # Next.js frontend
├── tests/
├── docker-compose.yml
└── CLAUDE.md
```

## ECS Deployment

**ECR Repository:** `434552667190.dkr.ecr.us-east-1.amazonaws.com/prediction-data`

```bash
# Build for Fargate (linux/amd64)
docker buildx build --platform linux/amd64 --load -t prediction-data:latest .

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 434552667190.dkr.ecr.us-east-1.amazonaws.com
docker tag prediction-data:latest 434552667190.dkr.ecr.us-east-1.amazonaws.com/prediction-data:latest
docker push 434552667190.dkr.ecr.us-east-1.amazonaws.com/prediction-data:latest
```

## Schema Changes

When adding new fields, update all three layers:
1. **Silver**: `src/prediction_data/silver/tables.py` + normalizer
2. **Gold**: `docker/clickhouse/init/*.sql` + `src/prediction_data/gold/dimensions.py`
3. **Reprocess**: `silver process --force-reprocess` then `gold load-dims`

See `CLAUDE_GRAVEYARD.md` for detailed schema change workflow.

---

**For detailed reference material** (ECS workflows, schema change examples, position accounting, etc.), see `CLAUDE_GRAVEYARD.md`.
