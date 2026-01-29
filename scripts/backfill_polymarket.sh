#!/usr/bin/env bash
#
# Backfill all Polymarket data (trades, markets, events) from 2023-01-01 to yesterday.
#
# Usage:
#   ./scripts/backfill_polymarket.sh                    # full backfill
#   ./scripts/backfill_polymarket.sh --dry-run           # preview only
#   ./scripts/backfill_polymarket.sh --start 2024-06-01  # custom start date
#   ./scripts/backfill_polymarket.sh --end 2024-12-31    # custom end date
#
# Required env vars (see .env.example):
#   BRONZE_BUCKET, POLYGON_WALLET_ADDRESS, POLYGON_WALLET_PRIVATE_KEY,
#   POLYMARKET_BUILDER_API_KEY, POLYMARKET_BUILDER_SECRET, POLYMARKET_BUILDER_PASSPHRASE

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

START_DATE="2023-01-01"
END_DATE="$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d 'yesterday' +%Y-%m-%d)"
DRY_RUN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --start)    START_DATE="$2"; shift 2 ;;
        --end)      END_DATE="$2"; shift 2 ;;
        --dry-run)  DRY_RUN="--dry-run"; shift ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Validate required env vars
for var in BRONZE_BUCKET POLYGON_WALLET_ADDRESS POLYGON_WALLET_PRIVATE_KEY POLYMARKET_BUILDER_API_KEY POLYMARKET_BUILDER_SECRET POLYMARKET_BUILDER_PASSPHRASE; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: $var is not set" >&2
        exit 1
    fi
done

echo "=== Polymarket Full Backfill ==="
echo "Date range: ${START_DATE} to ${END_DATE}"
echo "Bucket:     ${BRONZE_BUCKET}"
[[ -n "$DRY_RUN" ]] && echo "Mode:       DRY RUN"
echo ""

# Run each entity separately so a failure in one doesn't block the others.
# - trades: per-day backfill over the date range
# - markets/events: single full catalog fetch (not date-scoped)

FAILURES=()

# 1. Catalog fetches (markets & events) — run once, not per-day
for entity in markets events; do
    echo "--- Fetching full polymarket/${entity} catalog ---"
    if prediction-data backfill run \
        --start-date "$START_DATE" \
        --end-date "$END_DATE" \
        --platform polymarket \
        --entity "$entity" \
        $DRY_RUN; then
        echo "polymarket/${entity}: OK"
    else
        echo "polymarket/${entity}: FAILED" >&2
        FAILURES+=("$entity")
    fi
    echo ""
done

# 2. Trades backfill — per-day over the date range
echo "--- Backfilling polymarket/trades (${START_DATE} to ${END_DATE}) ---"
if prediction-data backfill run \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    --platform polymarket \
    --entity trades \
    $DRY_RUN; then
    echo "polymarket/trades: OK"
else
    echo "polymarket/trades: FAILED" >&2
    FAILURES+=("trades")
fi
echo ""

if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "=== Polymarket backfill finished with failures: ${FAILURES[*]} ===" >&2
    exit 1
else
    echo "=== Polymarket backfill complete ==="
fi
