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
#   BRONZE_BUCKET, POLYGON_WALLET_PUBLIC_KEY, POLYGON_WALLET_PRIVATE_KEY,
#   POLYMARKET_BUILDER_API_KEY, POLYMARKET_BUILDER_SECRET, POLYMARKET_BUILDER_PASSPHRASE

set -euo pipefail

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
for var in BRONZE_BUCKET POLYGON_WALLET_PRIVATE_KEY POLYMARKET_BUILDER_API_KEY POLYMARKET_BUILDER_SECRET POLYMARKET_BUILDER_PASSPHRASE; do
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

# Run trades, markets, and events backfills sequentially.
# Each entity is a separate run so a failure in one doesn't block the others.

for entity in trades markets events; do
    echo "--- Backfilling polymarket/${entity} ---"
    prediction-data backfill run \
        --start-date "$START_DATE" \
        --end-date "$END_DATE" \
        --platform polymarket \
        --entity "$entity" \
        $DRY_RUN
    echo ""
done

echo "=== Polymarket backfill complete ==="
