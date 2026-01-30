# CLAUDE.md

## Project Overview

Python data pipeline for ingesting prediction market data (Polymarket, Kalshi) into S3 bronze layer.

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

## Polymarket CLOB API

- **Base URL:** `https://clob.polymarket.com`
- **Trades endpoint:** `GET /data/trades`
- **Auth:** L2 HMAC-SHA256 — signs `timestamp + method + path` (query params excluded from signature)
- **Headers:** `POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_API_KEY`, `POLY_PASSPHRASE`
- **Pagination:** Cursor-based (`next_cursor` field). End sentinel: `LTE=`. No offset limit.
- **Page size:** Default 500 trades per page.

### CLOB Authentication Details

Two-tier auth system (L1 = wallet key, L2 = API credentials):

- **L1 (Private Key):** Signs EIP-712 messages. Used to create/derive API credentials.
- **L2 (API Credentials):** HMAC-SHA256 signing with `apiKey`, `secret`, `passphrase`.

**Generating/Deriving API Credentials:**

- **Create new:** `POST https://clob.polymarket.com/auth/api-key` (L1-authenticated)
- **Derive existing:** `GET https://clob.polymarket.com/auth/derive-api-key` (L1-authenticated)
- Response: `{ "apiKey": "...", "secret": "base64...", "passphrase": "..." }`

**Wallet/Signature Types (set during L2 init):**

| Type | Value | Description |
|---|---|---|
| EOA | 0 | Standard Ethereum wallet |
| POLY_PROXY | 1 | Magic Link / Google login proxy |
| GNOSIS_SAFE | 2 | Multisig proxy (most common for new users) |

The **funder address** (shown on polymarket.com profile) holds trading funds and must match the configured wallet type.

**To regenerate credentials:** Use the `py-clob-client` Python SDK or call the auth endpoints directly with L1 headers (`POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_NONCE=0`).

### Polymarket Gamma API

- **Base URL:** `https://gamma-api.polymarket.com`
- **Used for:** Markets and events snapshot ingestion.
- **Endpoints:** `GET /markets`, `GET /events`
- **Pagination:** Offset-based, no hard record limit (can return 100k+ records).

### Polymarket Data API (non-CLOB)

- **Base URL:** `https://data-api.polymarket.com`
- **Used for:** Non-backfill trades ingestion.
- **Pagination:** Offset-based with 10,000 record limit.

### Goldsky Subgraph API (OrderFilledEvents)

- **Endpoint:** `https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/orderbook-subgraph/prod/gn`
- **Used for:** OrderFilledEvent ingestion (on-chain order fill data).
- **Auth:** None (public subgraph).
- **Pagination:** Cursor-based using `id_gt` (standard subgraph pattern: `first:1000, orderBy:id, where:{id_gt:$cursor}`).
- **Filtering:** `timestamp_gte` / `timestamp_lte` for day boundaries (Unix epoch seconds).
- **Rate limits:** No documented hard limit; use configurable `page_delay` between requests.
- **Client:** `GoldskyClient` in `src/prediction_data/bronze/polymarket/goldsky.py`.

**OrderFilledEvent Schema (11 fields):**

| Field | Type | Notes |
|---|---|---|
| `id` | string | Subgraph entity ID |
| `transactionHash` | string | On-chain tx hash |
| `orderHash` | string | Order identifier |
| `timestamp` | int | Unix epoch seconds |
| `maker` | string | Maker address |
| `taker` | string | Taker address |
| `makerAssetId` | string | Maker asset token ID |
| `takerAssetId` | string | Taker asset token ID |
| `makerAmountFilled` | int | Base units (divide by 1e6 for USDC) |
| `takerAmountFilled` | int | Base units (divide by 1e6 for USDC) |
| `fee` | int | Fee in base units |

**Schema note:** Historical parquet-backfilled records are missing `orderHash`, `fee`, and `id` (set to null). Amounts in parquet source are scaled floats (e.g., 4.45 USDC) multiplied by 1e6 to match subgraph base units.

## Kalshi API

- **Base URL:** `https://api.elections.kalshi.com/trade-api/v2`
- **Auth:** RSA signature over timestamp + method + path.
- **Rate limits:** 10 requests/second per endpoint.
- **Trades pagination:** Cursor-based with `min_ts`/`max_ts` Unix timestamp filtering for date-scoped backfill.

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BRONZE_BUCKET` | Yes | S3 bucket for bronze layer data |
| `AWS_REGION` | No | AWS region (default: us-east-1) |
| `KALSHI_API_KEY_ID` | For Kalshi | Kalshi API key ID |
| `KALSHI_PRIVATE_KEY_PATH` | For Kalshi | Path to Kalshi RSA private key |
| `POLYGON_WALLET_ADDRESS` | For CLOB | CLOB API-derived address (used in POLY_ADDRESS header) |
| `POLYGON_WALLET_PUBLIC_KEY` | For CLOB | Polygon wallet public key |
| `POLYGON_WALLET_PRIVATE_KEY` | For CLOB | Polygon wallet private key |
| `POLYMARKET_BUILDER_API_KEY` | For CLOB | Builder API key |
| `POLYMARKET_BUILDER_SECRET` | For CLOB | Base64-encoded Builder API secret |
| `POLYMARKET_BUILDER_PASSPHRASE` | For CLOB | Builder API passphrase |

## Backfill CLI

```bash
# Backfill all platforms/entities for a date range
prediction-data backfill run --start-date 2024-01-01 --end-date 2024-01-31

# Backfill only Polymarket trades
prediction-data backfill run --start-date 2024-06-01 --end-date 2024-06-30 \
    --platform polymarket --entity trades

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

- Polymarket trades backfill uses the CLOB API (cursor-based, no record limit).
- Kalshi trades backfill uses `min_ts`/`max_ts` to scope each day.
- Markets/events run existing snapshot ingestion per day.
- On per-day failure, continues to next day and prints failure summary at end.
- Sequential processing only (concurrency deferred).

## S3 Key Structure

```
bronze/{platform}/{entity}/dt={YYYY-MM-DD}/run_id={uuid}/
  ├── part-000.json
  ├── part-001.json
  └── _manifest.json
```

## Data Volumes (Estimates)

- **Polymarket trades:** ~5,000-50,000 trades/day (varies with market activity). At 500/page, expect 10-100 API calls per day.
- **Kalshi trades:** ~1,000-10,000 trades/day.
- **Polymarket markets catalog:** ~360,000 records (~163 MB gzipped). Full fetch takes ~48 min at 100/page.
- **Polymarket events catalog:** ~176,000 records (~165 MB gzipped). Full fetch takes ~19 min at 100/page.
- **Full historical trades backfill** (e.g., 1 year): Expect several hours of sequential processing due to rate limiting.
