#!/usr/bin/env bash
#
# Daily Gold processing wrapper for cron/EventBridge execution.
#
# Runs the full Gold daily pipeline:
#   1. prediction-data gold daily-run  (load dims, process trades, compute marks, compute wallet metrics)
#   2. prediction-data gold ch-load --all  (load all Gold tables into ClickHouse)
#   3. prediction-data gold freshness  (verify all datasets are fresh)
#
# Usage:
#   ./scripts/gold_daily_cron.sh                      # full daily pipeline (yesterday)
#   ./scripts/gold_daily_cron.sh --dt 2026-02-01      # specific date
#   ./scripts/gold_daily_cron.sh --dry-run             # preview only
#   ./scripts/gold_daily_cron.sh --lookback-days 30    # custom CH lookback
#
# Required env vars (see .env.example):
#   GOLD_BUCKET
#
# Optional env vars:
#   CLICKHOUSE_HOST, CLICKHOUSE_PORT (defaults: localhost, 8123)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

DT_FLAG=""
DRY_RUN=""
LOOKBACK_DAYS=90

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dt)           DT_FLAG="--dt $2"; shift 2 ;;
        --dry-run)      DRY_RUN="--dry-run"; shift ;;
        --lookback-days) LOOKBACK_DAYS="$2"; shift 2 ;;
        *)              echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Validate required env vars.
for var in GOLD_BUCKET; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: $var is not set" >&2
        exit 1
    fi
done

echo "=== Gold Daily Pipeline ==="
echo "Bucket:         ${GOLD_BUCKET}"
echo "CH Lookback:    ${LOOKBACK_DAYS} days"
[[ -n "$DT_FLAG" ]] && echo "Date override:  ${DT_FLAG}"
[[ -n "$DRY_RUN" ]] && echo "Mode:           DRY RUN"
echo ""

FAILURES=()

# Step 1: Daily Gold processing (dims, trades, marks, wallet metrics)
echo "--- Step 1: Gold daily-run ---"
if prediction-data gold daily-run $DT_FLAG $DRY_RUN; then
    echo "gold daily-run: OK"
else
    echo "gold daily-run: FAILED (continuing)" >&2
    FAILURES+=("daily-run")
fi
echo ""

# Step 2: Load all Gold tables into ClickHouse
echo "--- Step 2: Gold ch-load --all ---"
if prediction-data gold ch-load --all --lookback-days "$LOOKBACK_DAYS" $DRY_RUN; then
    echo "gold ch-load: OK"
else
    echo "gold ch-load: FAILED (continuing)" >&2
    FAILURES+=("ch-load")
fi
echo ""

# Step 3: Freshness check
echo "--- Step 3: Gold freshness check ---"
if prediction-data gold freshness; then
    echo "gold freshness: OK"
else
    echo "gold freshness: FAILED (continuing)" >&2
    FAILURES+=("freshness")
fi
echo ""

if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "=== Gold daily pipeline finished with failures: ${FAILURES[*]} ===" >&2
    exit 1
else
    echo "=== Gold daily pipeline complete ==="
fi
