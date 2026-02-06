# CLAUDE.md

## Project Overview

Python data pipeline for ingesting prediction market data (Polymarket, Kalshi) into S3 bronze layer, normalizing it into Silver Iceberg tables (Glue Catalog, Parquet/ZSTD, day-partitioned), and computing Gold aggregations (position accounting, PnL, market marks) served via ClickHouse.

## Release & Sprint Plans

Project work is organized into releases and sprints under `plans/release/`.

```
plans/release/
├── 01_bronze_level/
│   ├── RELEASE.md              # Release scope, goals, exit criteria
│   ├── progress.txt            # Release-level progress tracking
│   └── sprint/
│       ├── 01_project_bootstrap/
│       │   ├── prd.json        # Sprint PRD: categories with steps and pass/fail
│       │   └── progress.txt    # Sprint progress log
│       ├── 02_core_infra/
│       ├── ...
│       └── 08_order_filled_ingestion/
├── 02_silver_level/
│   └── RELEASE.md
└── 03_gold_level/
    └── RELEASE.md
```

- **RELEASE.md**: Defines scope, exit criteria, entities, and architecture for a release.
- **prd.json**: Array of `{ category, description, steps[], passes }` objects. `passes` is `true`/`false` indicating completion.
- **progress.txt**: Free-form log of completed tasks, blockers, and notes per sprint.
- Use `/sprint_generator <release_name>` to generate sprints from a RELEASE.md.

## Quick Reference

```bash
# Install
pip install -e ".[dev]"

# Run tests (excludes integration tests)
pytest -m "not integration"

# Type check
mypy src/

# Lint
ruff check src/ tests/

# Start local infrastructure (PostgreSQL + ClickHouse)
docker compose up -d
# Verify: docker compose exec postgres pg_isready -U predmkts
# Verify: docker compose exec clickhouse clickhouse-client --query "SELECT 1"
# Stop: docker compose down

# Docker Compose profiles (optional services)
docker compose --profile api up -d      # Include API service (containerized)
docker compose --profile cache up -d    # Include Redis for caching
docker compose --profile api --profile cache up -d  # All services

# CLI entry point
prediction-data --help
```

## Polymarket Rate Limits

Full reference: https://docs.polymarket.com/quickstart/introduction/rate-limits

### Endpoints We Hit

| API | Endpoint | Rate Limit |
|---|---|---|
| CLOB | `GET /data/trades` | 500 req/10s |
| Gamma | `GET /markets` | 300 req/10s |
| Gamma | `GET /events` | 500 req/10s |
| Data | `GET /trades` | 200 req/10s |
| Goldsky | `POST /subgraphs/.../gn` | No hard limit (use page_delay) |

### Full Rate Limits by API

**CLOB API** (`clob.polymarket.com`): 9,000 req/10s overall. `/data/trades`: 500/10s.

**Gamma API** (`gamma-api.polymarket.com`): 4,000 req/10s overall. `/markets`: 300/10s. `/events`: 500/10s.

**Data API** (`data-api.polymarket.com`): 1,000 req/10s overall. `/trades`: 200/10s.

## API References

Detailed endpoint parameters, response schemas, and pagination details are in `docs/api/`:

**Polymarket:**
- [`docs/api/polymarket-gamma.md`](docs/api/polymarket-gamma.md) — Gamma API (markets, events). Supports `start_date_min` for incremental fetch. No `updated_since` filter.
- [`docs/api/polymarket-clob.md`](docs/api/polymarket-clob.md) — CLOB API (trades, auth, orders). L2 HMAC-SHA256 auth. Cursor-based pagination.
- [`docs/api/polymarket-data.md`](docs/api/polymarket-data.md) — Data API (trades, positions). Offset-based with 10k limit.
- [`docs/api/polymarket-goldsky.md`](docs/api/polymarket-goldsky.md) — Goldsky subgraph (OrderFilledEvents). GraphQL, cursor-based via `id_gt`.

**Kalshi:**
- [`docs/api/kalshi.md`](docs/api/kalshi.md) — Full API (trades, markets, events, series). RSA-PSS auth. Cursor-based pagination. Supports `min_updated_ts` for true incremental market ingestion.

**Consult these files before making claims about what API parameters are or aren't available.**

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BRONZE_BUCKET` | Yes | S3 bucket for bronze layer data |
| `GOLD_BUCKET` | For Gold | S3 bucket for Gold layer Parquet files |
| `CLICKHOUSE_HOST` | For Gold | ClickHouse server hostname (default: localhost) |
| `CLICKHOUSE_PORT` | For Gold | ClickHouse native port (default: 9000) |
| `CLICKHOUSE_USER` | For Gold | ClickHouse username (default: default) |
| `CLICKHOUSE_PASSWORD` | For Gold | ClickHouse password (default: empty) |
| `CLICKHOUSE_DATABASE` | For Gold | ClickHouse database (default: prediction_gold) |
| `AWS_REGION` | No | AWS region (default: us-east-1) |
| `KALSHI_API_KEY_ID` | For Kalshi | Kalshi API key ID |
| `KALSHI_PRIVATE_KEY_PATH` | For Kalshi | Path to Kalshi RSA private key |
| `POLYGON_WALLET_ADDRESS` | For CLOB | CLOB API-derived address (used in POLY_ADDRESS header) |
| `POLYGON_WALLET_PUBLIC_KEY` | For CLOB | Polygon wallet public key |
| `POLYGON_WALLET_PRIVATE_KEY` | For CLOB | Polygon wallet private key |
| `POLYMARKET_BUILDER_API_KEY` | For CLOB | Builder API key |
| `POLYMARKET_BUILDER_SECRET` | For CLOB | Base64-encoded Builder API secret |
| `POLYMARKET_BUILDER_PASSPHRASE` | For CLOB | Builder API passphrase |

## REST API

The project exposes a REST API for frontend integration, built with FastAPI.

### Running the API

```bash
# Start the API server (development)
uvicorn prediction_data.api.main:app --reload

# API will be available at http://localhost:8000
# Interactive docs (Swagger UI): http://localhost:8000/docs
# ReDoc documentation: http://localhost:8000/redoc
# OpenAPI JSON: http://localhost:8000/openapi.json
```

### API Versioning Strategy

All API endpoints follow URL-based versioning with `/api/v1/` prefix:

- **Current version:** `v1` (0.1.0)
- **Versioning scheme:** URL path prefix (`/api/v1/`, `/api/v2/`, etc.)
- **Health endpoints:** Not versioned (available at `/health`, `/health/ready`, `/health/live`)

**Endpoint structure:**
```
/api/v1/auth/*           # Authentication (register, login, refresh, me)
/api/v1/markets/*        # Market data and search
/api/v1/traders/*        # Trader profiles and leaderboards
/api/v1/watchlist/*      # User watchlist management
/api/v1/tracked-traders/* # Tracked traders management
/api/v1/trades/*         # Trade data (smart money, whales)
/api/v1/events/*         # Event data
/health                  # Health checks (not versioned)
```

**Version migration policy:**
- Breaking changes require a new version (`v2`, `v3`, etc.)
- Non-breaking additions (new fields, endpoints) can be added to existing version
- Old versions will be maintained for at least 6 months after deprecation notice
- Deprecation will be communicated via `Deprecation` header and documentation

### API Rate Limits

| Endpoint Category | Rate Limit | Notes |
|---|---|---|
| Auth endpoints | 10 req/min per IP | Brute force prevention |
| Public read endpoints | 100 req/min per IP | Markets, traders, events |
| Authenticated endpoints | 200 req/min per user | Watchlist, tracked traders |
| CLOB proxy endpoints | 50 req/min | Stay under Polymarket limits |

Rate limit headers returned: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After` (on 429).

### Error Response Format

All API errors return a consistent JSON structure:

```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE",
  "status": 400
}
```

Common error codes:
- `VALIDATION_ERROR` (422) — Request validation failed, includes `errors` array with field-level details
- `AUTHENTICATION_FAILED` (401) — Invalid or expired credentials
- `AUTHORIZATION_DENIED` (403) — Permission denied (e.g., tier limits exceeded)
- `NOT_FOUND` (404) — Resource not found
- `RATE_LIMIT_EXCEEDED` (429) — Rate limit hit, includes `retry_after` field

### Environment Variables (API)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | Secret for JWT signing (min 32 chars) |
| `JWT_ALGORITHM` | No | JWT algorithm (default: HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token TTL (default: 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | Refresh token TTL (default: 7) |
| `DEBUG` | No | Enable debug mode with stack traces (default: false) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins, or `*` for dev (default: *) |

## Frontend (Next.js)

The frontend is a Next.js application in `web/` that integrates with the FastAPI backend.

### Running the Frontend

```bash
cd web

# Install dependencies
npm install

# Start development server (proxies /api/v1/* to FastAPI backend)
npm run dev

# Build for production
npm run build
npm start

# Type checking
npm run typecheck

# Run tests
npm run test

# Lint
npm run lint
```

### Frontend-Backend Integration

The frontend communicates with the FastAPI backend through:

1. **API Proxy (Development)**: `next.config.ts` proxies `/api/v1/*` requests to `http://localhost:8000` (or `API_URL` env var). This avoids CORS issues in development.

2. **API Client** (`web/src/lib/api/client.ts`):
   - `apiRequest<T>()` — Generic fetch wrapper with auth handling
   - Automatic JWT token management (localStorage)
   - Automatic token refresh on 401 responses
   - Consistent error handling via `ApiError` class

3. **Auth Context** (`web/src/lib/api/auth-context.tsx`):
   - React context for authentication state
   - `login()`, `logout()`, `register()` methods
   - User state management with automatic token restoration

4. **Generated Types** (`web/src/lib/api/schema.d.ts`):
   - TypeScript types generated from OpenAPI spec
   - Ensures frontend/backend type safety

### Regenerating TypeScript Types

When the API schema changes (new endpoints, modified responses), regenerate the frontend types:

```bash
# Generate OpenAPI spec from FastAPI
cd /path/to/repo
uvicorn prediction_data.api.main:app --reload &
curl http://localhost:8000/openapi.json > openapi.json

# Generate TypeScript types
cd web
npm run generate-api
```

This creates `web/src/lib/api/schema.d.ts` from `openapi.json`.

### Environment Variables (Frontend)

| Variable | Required | Description |
|---|---|---|
| `API_URL` | No | Backend API URL for proxy (default: http://localhost:8000) |
| `NEXT_PUBLIC_API_URL` | No | Client-side API URL if not using proxy |

## Full Stack Development

### Docker Compose Services

The project uses Docker Compose to manage local infrastructure:

| Service | Description | Default Port | Profile |
|---|---|---|---|
| `postgres` | PostgreSQL database for user data | 5432 | (always) |
| `clickhouse` | ClickHouse for analytics/Gold layer | 8123, 9000 | (always) |
| `redis` | Redis for distributed caching (optional) | 6379 | `cache` |
| `api` | FastAPI server (optional, containerized) | 8000 | `api` |

**Profiles** allow optional services to be included:
```bash
docker compose up -d                           # postgres + clickhouse only
docker compose --profile cache up -d           # include Redis
docker compose --profile api up -d             # include API container
docker compose --profile api --profile cache up -d  # all services
```

**Override file**: `docker-compose.override.yml` is automatically loaded and adds:
- Query logging for postgres (log_statement=all)
- Hot reload for the API container (mounts `./src` volume)
- Development-friendly defaults (DEBUG=true, CORS_ORIGINS=*)

For production, skip the override file: `docker compose -f docker-compose.yml up -d`

### Running Everything Locally

```bash
# 1. Start infrastructure (PostgreSQL + ClickHouse)
docker compose up -d

# 2. Wait for healthy databases (healthchecks should pass automatically)
docker compose exec postgres pg_isready -U predmkts
docker compose exec clickhouse clickhouse-client --query "SELECT 1"

# 3. Start FastAPI backend (in one terminal)
uvicorn prediction_data.api.main:app --reload
# API: http://localhost:8000
# Docs: http://localhost:8000/docs

# 4. Start Next.js frontend (in another terminal)
cd web && npm run dev
# Frontend: http://localhost:3000
# Proxies /api/v1/* to backend automatically
```

**Alternative: Fully Containerized**
```bash
# Run everything in containers (no local Python/Node.js needed)
docker compose --profile api up -d

# Frontend still runs locally (for hot reload during development)
cd web && npm run dev
```

### Development Workflow

1. **Schema Changes**: Modify Pydantic schemas in `src/prediction_data/api/*/schemas.py`
2. **Regenerate Types**: Run `npm run generate-api` in `web/`
3. **Type Check**: Run `npm run typecheck` to verify frontend compatibility
4. **Test**: Run `pytest tests/api/` for backend, `npm run test` for frontend

### Project Structure

```
predmkts_backend/
├── src/prediction_data/
│   ├── api/                    # FastAPI REST API
│   │   ├── main.py             # App entry point, middleware
│   │   ├── auth/               # Authentication endpoints
│   │   ├── markets/            # Market data endpoints
│   │   ├── traders/            # Trader data endpoints
│   │   ├── watchlist/          # User watchlist endpoints
│   │   ├── tracked_traders/    # Tracked traders endpoints
│   │   ├── trades/             # Trade data endpoints
│   │   ├── events/             # Event data endpoints
│   │   ├── health.py           # Health check endpoints
│   │   ├── exceptions.py       # Custom exception classes
│   │   ├── middleware.py       # Request logging, security headers
│   │   ├── rate_limit.py       # Rate limiting configuration
│   │   └── validators.py       # Reusable Pydantic validators
│   ├── bronze/                 # Bronze layer ingestion
│   ├── silver/                 # Silver layer processing
│   ├── gold/                   # Gold layer aggregations
│   └── core/                   # Shared configuration
├── web/                        # Next.js frontend
│   ├── src/
│   │   ├── app/                # Next.js app router pages
│   │   ├── components/         # React components
│   │   ├── hooks/              # Custom React hooks
│   │   └── lib/
│   │       └── api/            # API client and types
│   └── next.config.ts          # Next.js config with API proxy
├── tests/
│   ├── api/                    # API integration tests
│   └── ...                     # Other test modules
├── docker-compose.yml          # Local infrastructure
├── openapi.json                # Generated OpenAPI spec
└── CLAUDE.md                   # This file
```

## Backfill CLI

```bash
# Backfill all platforms/entities for a date range
prediction-data backfill run --start-date 2024-01-01 --end-date 2024-01-31

# Backfill only Polymarket order_filled
prediction-data backfill run --start-date 2024-06-01 --end-date 2024-06-30 \
    --platform polymarket --entity order_filled

# Dry run (preview without executing)
prediction-data backfill run --start-date 2024-01-01 --end-date 2024-01-07 --dry-run

# Kalshi trades backfill (uses min_ts/max_ts day boundaries)
prediction-data backfill run --start-date 2024-01-01 --end-date 2024-01-31 \
    --platform kalshi --entity trades

# Ingest Polymarket order_filled events for a single day
prediction-data ingest polymarket-order-filled --dt 2024-06-15

# Backfill order_filled via Goldsky subgraph
prediction-data backfill run --start-date 2024-06-01 --end-date 2024-06-30 \
    --platform polymarket --entity order_filled
```

### Catchup (Auto-Detect & Backfill to Present)

```bash
# Catch up all platforms/entities to present
prediction-data backfill catchup

# Catch up only Polymarket order_filled (incremental — fetches only new records)
prediction-data backfill catchup --platform polymarket --entity order_filled

# Force full snapshot for catalog entities (markets/events) instead of incremental
prediction-data backfill catchup --full

# Preview what would be fetched
prediction-data backfill catchup --dry-run
```

**Incremental modes by entity type:**
- **Catalog entities (markets, events):** Catchup uses incremental ingestion by default — finds the latest manifest, extracts the `updatedAt` cursor, and fetches only records changed since then via Gamma API (`order=updatedAt&ascending=false`). Writes delta partitions with `snapshot_type="delta"`. Use `--full` to force a full snapshot instead. Falls back to full snapshot automatically on first run or if no cursor exists.
- **order_filled:** Incremental via Goldsky subgraph — finds the latest timestamp and fetches only newer records.
- **Kalshi trades:** Finds the latest date and backfills missing days.

### Parquet-to-Bronze Backfill (order_filled)

Convert historical parquet data to bronze JSONL.gz format. Reads from the monolithic
`s3://polymarket-bcp892/raw/polymarket/order_filled.parquet` (~15 GB, 313M rows),
streams row groups to avoid loading everything into memory, and filters by date.

The script uses a single-pass scan over all row groups, bucketing rows by date as they
are read. This streams the 15 GB file exactly once regardless of how many days are in the
range — O(row_groups) vs the naive O(days * row_groups) that would re-scan per day.

Token ID resolution: Asset IDs in the parquet are float-notation strings (e.g. `6.58e+76`)
due to precision loss. The script builds a mapping from bronze markets JSONL data
(`clobTokenIds` field) to resolve them to full-precision token IDs.

```bash
# Convert a date range from the monolithic parquet
python scripts/backfill_order_filled_from_parquet.py \
    --start-date 2022-11-01 --end-date 2026-01-31

# Preview without writing to S3
python scripts/backfill_order_filled_from_parquet.py \
    --start-date 2024-01-01 --end-date 2024-03-31 --dry-run
```

- Kalshi trades backfill uses `min_ts`/`max_ts` to scope each day.
- Markets/events run existing snapshot ingestion per day.
- On per-day failure, continues to next day and prints failure summary at end.
- Sequential processing only (concurrency deferred).

## Status CLI

```bash
# Check data coverage for a date range (shows gaps)
prediction-data status coverage --start-date 2024-01-01 --end-date 2024-01-31
prediction-data status coverage --start-date 2024-01-01 --end-date 2024-01-31 \
    --platform polymarket --entity trades

# List recent ingestion runs (default: last 20)
prediction-data status runs
prediction-data status runs --platform kalshi --last 10
prediction-data status runs --dt 2024-06-15  # all runs for a specific date

# Show full details of a specific run
prediction-data status show-run <run_id>

# Validate manifest integrity and detect orphaned/incomplete data
prediction-data status validate --start-date 2024-01-01 --end-date 2024-01-31
prediction-data status validate --start-date 2024-06-01 --end-date 2024-06-30 \
    --platform polymarket --entity trades
```

## Silver CLI

```bash
# Initialize all Silver Iceberg tables in Glue Catalog
prediction-data silver init-tables
prediction-data silver init-tables --dry-run

# Catch up Silver processing to present (near-continuous mode)
# Auto-detects latest processed date from state store, discovers new Bronze manifests
prediction-data silver catchup --platform polymarket --entity trades
prediction-data silver catchup --platform polymarket --entity trades --dry-run
prediction-data silver catchup --platform polymarket --entity trades --from-date 2025-01-15

# Catchup with ECS concurrency guard (used by EventBridge schedules)
# Exits cleanly if another task for the same entity is already running
prediction-data silver catchup --platform polymarket --entity trades --skip-if-concurrent

# Process Bronze manifests into Silver Iceberg tables (manual/backfill)
prediction-data silver process --platform polymarket --entity trades --dt 2024-06-15
prediction-data silver process --platform polymarket --entity markets \
    --start-date 2024-06-01 --end-date 2024-06-30
prediction-data silver process --platform polymarket --entity trades \
    --start-date 2024-06-01 --end-date 2024-06-30 --dry-run
prediction-data silver process --platform polymarket --entity trades \
    --dt 2024-06-15 --force-reprocess --skip-quality-checks

# Compact small files in an Iceberg table
prediction-data silver compact --table polymarket/trades
prediction-data silver compact --table polymarket/trades --partition 2024-06-15
prediction-data silver compact --table polymarket/trades --dry-run

# Expire old snapshots (default: older than 7 days)
prediction-data silver expire-snapshots --table polymarket/trades
prediction-data silver expire-snapshots --table polymarket/trades --older-than-days 14

# Remove orphaned data files
prediction-data silver remove-orphans --table polymarket/trades
prediction-data silver remove-orphans --table polymarket/trades --dry-run

# Run all maintenance operations across all Silver tables
prediction-data silver maintain
prediction-data silver maintain --op compact              # compaction only
prediction-data silver maintain --op expire --op orphans  # expiration + orphan cleanup
prediction-data silver maintain --dry-run
prediction-data silver maintain --skip-if-concurrent      # with ECS concurrency guard
```

**Near-continuous scheduling (EventBridge):**
- **Trades:** every 10 min via `silver catchup --skip-if-concurrent`
- **Catalog (markets, events):** every 30 min via `silver catchup --skip-if-concurrent`
- **Daily maintenance:** `silver maintain --op compact --skip-if-concurrent` at 04:00 UTC
- **Weekly maintenance:** `silver maintain --skip-if-concurrent` Sundays at 04:00 UTC

Concurrency is scoped per entity type (`silver-{platform}-{entity}`) so different entities can run concurrently but the same entity type cannot overlap. Maintenance uses filter `silver-maintain`.

**Valid platform/entity targets:** polymarket/trades, polymarket/markets, polymarket/events, kalshi/trades, kalshi/markets, kalshi/events.

**Processing features:**
- Manifest-driven: discovers Bronze manifests and processes them into Iceberg tables.
- Idempotent: tracks processed manifests in S3 state store; use `--force-reprocess` to override.
- Snapshot-supersedes-deltas: for catalog entities (markets, events), a snapshot manifest supersedes earlier delta manifests for the same day.
- Quality checks: non-null, uniqueness, timestamp range checks run by default; use `--skip-quality-checks` to bypass.

## Gold CLI

```bash
# Run all daily Gold processing steps (load-dims → process-trades → compute-marks → compute-wallet-metrics)
prediction-data gold daily-run
prediction-data gold daily-run --dt 2024-06-15
prediction-data gold daily-run --dry-run

# Load dimension tables into S3 and ClickHouse
prediction-data gold load-dims
prediction-data gold load-dims --table dim_market --dry-run

# Process Silver trades through position accounting pipeline (ledger + position state)
prediction-data gold process-trades --dt 2024-06-15
prediction-data gold process-trades --start-date 2024-06-01 --end-date 2024-06-30
prediction-data gold process-trades --dt 2024-06-15 --force-reprocess --dry-run

# Compute market marks (VWAP, last price, volume) from Silver trades
prediction-data gold compute-marks --dt 2024-06-15 --platform polymarket
prediction-data gold compute-marks --start-date 2024-06-01 --end-date 2024-06-30

# Compute wallet PnL daily (aggregated from position ledger)
prediction-data gold compute-pnl --dt 2024-06-15
prediction-data gold compute-pnl --start-date 2024-06-01 --end-date 2024-06-30

# Compute wallet MTM daily (watchlist wallets only)
prediction-data gold compute-mtm --dt 2024-06-15

# Compute wallet position snapshots (watchlist wallets only)
prediction-data gold compute-position-snapshot --dt 2024-06-15

# Compute all wallet metrics in one command
prediction-data gold compute-wallet-metrics --dt 2024-06-15

# Load Gold tables from S3 into ClickHouse
prediction-data gold ch-load --table market_mark_daily --lookback-days 90
prediction-data gold ch-load --all --lookback-days 90

# On-demand wallet snapshot reconstruction
prediction-data gold compute-snapshot --wallet 0x123... --start-date 2024-01-01 --end-date 2024-06-30

# Rebuild Gold tables from Silver for a date range
prediction-data gold rebuild --table market_mark_daily --start-date 2024-06-01 --end-date 2024-06-30
prediction-data gold rebuild --table wallet_pnl_daily --start-date 2024-06-01 --end-date 2024-06-30 --force

# Display freshness status of all Gold datasets
prediction-data gold freshness

# Watchlist management
prediction-data gold watchlist add 0x123...
prediction-data gold watchlist remove 0x123...
prediction-data gold watchlist list
prediction-data gold watchlist list --all  # include inactive
```

**Scheduled processing (EventBridge):**
- **daily-run:** midnight UTC — runs all daily processing steps
- **ch-load:** 00:30 UTC — loads all Gold tables to ClickHouse (90-day lookback)
- **freshness:** 01:00 UTC — verifies all datasets are within SLA

**Gold tables:**
- `dim_platform`, `dim_market`, `dim_outcome`, `dim_wallet`, `dim_event`, `dim_category` — dimension tables
- `wallet_position_ledger` — per-fill position accounting records
- `wallet_position_state` — current position state per wallet/market/outcome
- `market_mark_daily` — daily market marks (VWAP, last price, volume, liquidity)
- `wallet_pnl_daily` — daily realized PnL per wallet (all wallets)
- `wallet_mtm_daily` — daily mark-to-market per wallet (watchlist only)
- `wallet_position_snapshot_daily` — daily position snapshots (watchlist only)

**Position accounting methodology:**
- Average-cost basis: `new_avg_cost = (old_qty * old_avg_cost + qty_delta * price) / new_qty`
- Realized PnL on close: `pnl = closed_qty * (exit_price - avg_cost) - fees`
- Position flips: oversized sell splits into close (realize PnL) + open (new direction)
- Ledger records before/after state snapshots for full audit trail

**Freshness SLAs (seconds):**
- `market_mark_daily`: 300 (5 min)
- `wallet_pnl_daily`: 600 (10 min)
- `wallet_mtm_daily`: 900 (15 min)
- `wallet_position_snapshot_daily`: 900 (15 min)

Freshness states: `fresh` (within SLA), `stale` (SLA < lag <= 2×SLA), `broken` (lag > 2×SLA or last run failed).

See [`docs/gold-operations-runbook.md`](docs/gold-operations-runbook.md) for full operational procedures.

## Pipeline Diagnostics

The `scripts/diagnose_markets.py` script provides comprehensive diagnostics for the markets data pipeline, tracing data from external APIs through Bronze, Silver, Gold layers to the REST API.

```bash
# Run full diagnostics
python scripts/diagnose_markets.py
```

**What it checks:**

| Layer | Checks |
|-------|--------|
| External API | Polymarket Gamma API connectivity and schema validation |
| Bronze | S3 manifests, record counts, ingestion freshness |
| Silver | Iceberg table snapshots, row counts, staleness |
| Gold | ClickHouse table row counts (dim_market, dim_outcome, dim_event, market_mark_daily) |
| REST API | Endpoint response, market data completeness, outcome population |
| Infrastructure | EventBridge schedule status (enabled/disabled) |

**Output includes:**
- Color-coded status indicators (OK/WARN/ERROR)
- Natural language explanations for each pipeline stage
- Data freshness with human-readable ages ("2h ago", "1d ago")
- Recommended fixes for common issues
- Summary of all issues and warnings

**Common issues detected:**
- Empty dimension tables (e.g., `dim_outcome` empty causes blank API responses)
- Stale data at any layer (Bronze not ingesting, Silver not processing)
- Missing manifests or snapshots
- API returning incomplete market data

**Example output:**
```
================================================================================
  4. GOLD LAYER (ClickHouse)
================================================================================
  [OK] dim_market: 386,588 rows
  [ERROR] dim_outcome: 0 rows - EMPTY - This is why API returns blank data!
  [OK] dim_event: 181,756 rows
  [WARN] market_mark_daily: Latest: 2026-02-04 (2d old)

================================================================================
  RECOMMENDED FIXES
================================================================================
  1. Load dim_outcome table:
     Run: prediction-data gold load-dims --table dim_outcome
```

## S3 Key Structure

**Bronze:**
```
bronze/{platform}/{entity}/dt={YYYY-MM-DD}/run_id={uuid}/
  ├── part-000.json
  ├── part-001.json
  └── _manifest.json
```

**Gold:**
```
gold/{table_name}/day={YYYY-MM-DD}/part-000.parquet
```

## Data Volumes (Estimates)

- **Polymarket order_filled:** ~50,000-500,000 events/day (varies with market activity). Trades are constructed in Silver from these events.
- **Kalshi trades:** ~1,000-10,000 trades/day.
- **Polymarket markets catalog:** ~360,000 records (~163 MB gzipped). Full fetch takes ~10 min at 500/page.
- **Polymarket events catalog:** ~176,000 records (~165 MB gzipped). Full fetch takes ~4 min at 500/page.
- **Full historical Kalshi trades backfill** (e.g., 1 year): Expect several hours of sequential processing due to rate limiting.
