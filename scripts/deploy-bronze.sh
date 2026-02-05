#!/usr/bin/env bash
# =============================================================================
# Bronze Release 01 - EventBridge Schedules Deployment
#
# Deploys the Bronze layer EventBridge schedules CloudFormation stack.
# Run this after any changes to infrastructure/eventbridge-schedules.yaml
#
# Steps:
#   Step 1: Deploy EventBridge Bronze schedules
#   Step 2: Post-deployment verification
#   Step 3: Trigger immediate catchup (optional)
#
# Usage:
#   ./scripts/deploy-bronze.sh              # Run all steps interactively
#   ./scripts/deploy-bronze.sh --dry-run    # Preview without executing
#   ./scripts/deploy-bronze.sh --skip-catchup  # Skip the manual catchup trigger
# =============================================================================

set -euo pipefail

# --- Configuration (discovered from live environment) ---
AWS_REGION="us-east-1"
ENV="prod"
ECS_CLUSTER_ARN="arn:aws:ecs:us-east-1:434552667190:cluster/prediction-data-prod"
TASK_DEF_ARN="arn:aws:ecs:us-east-1:434552667190:task-definition/prediction-data-ingest-prod:1"
SUBNET_IDS="subnet-64b44845"
SECURITY_GROUP_IDS="sg-1d625733"
LOG_GROUP_NAME="/ecs/prediction-data-prod"

# --- Internal state ---
DRY_RUN=false
SKIP_CATCHUP=false
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="${SCRIPT_DIR}/infrastructure"
LOG_FILE="/tmp/deploy-bronze-$(date +%Y%m%d-%H%M%S).log"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --skip-catchup) SKIP_CATCHUP=true; shift ;;
        --help)
            echo "Usage: $0 [--dry-run] [--skip-catchup]"
            echo ""
            echo "Options:"
            echo "  --dry-run       Preview without executing"
            echo "  --skip-catchup  Skip the manual catchup trigger"
            echo ""
            echo "Steps:"
            echo "  1  Deploy EventBridge Bronze schedules"
            echo "  2  Post-deployment verification"
            echo "  3  Trigger immediate catchup (unless --skip-catchup)"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC} $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" | tee -a "$LOG_FILE" >&2; }
header() { echo -e "\n${BOLD}${BLUE}=== $* ===${NC}\n" | tee -a "$LOG_FILE"; }

run_cmd() {
    local desc="$1"; shift
    log "$desc"
    echo "  -> $*" | tee -a "$LOG_FILE"
    if [ "$DRY_RUN" = true ]; then
        echo -e "  ${YELLOW}[DRY RUN] Skipped${NC}"
        return 0
    fi
    if "$@" 2>&1 | tee -a "$LOG_FILE"; then
        echo -e "  ${GREEN}OK${NC}"
    else
        err "Command failed: $*"
        return 1
    fi
}

confirm() {
    if [ "$DRY_RUN" = true ]; then return 0; fi
    echo -e "${YELLOW}$1${NC}"
    read -rp "Continue? [y/N] " response
    [[ "$response" =~ ^[Yy]$ ]]
}

# --- Preflight ---
header "Bronze Release 01 - EventBridge Schedules Deployment"
log "Environment: $ENV"
log "Region: $AWS_REGION"
log "Dry Run: $DRY_RUN"
log "Skip Catchup: $SKIP_CATCHUP"
log "Log file: $LOG_FILE"
echo ""

if ! aws sts get-caller-identity --region "$AWS_REGION" &>/dev/null; then
    err "AWS credentials not configured."
    exit 1
fi
log "AWS Account: $(aws sts get-caller-identity --query Account --output text)"

# =========================================================================
# STEP 1: Deploy EventBridge Bronze Schedules
# =========================================================================
header "Step 1: Deploy EventBridge Bronze Schedules"
log "This updates the CloudFormation stack with 6 EventBridge schedules:"
log "  High-frequency (every 5 min):"
log "    - polymarket-order-filled-prod   (backfill catchup)"
log "    - kalshi-trades-prod             (backfill catchup)"
log "  Catalog (every 1 hour):"
log "    - polymarket-markets-prod        (ingest)"
log "    - polymarket-events-prod         (ingest)"
log "    - kalshi-markets-prod            (ingest)"
log "    - kalshi-events-prod             (ingest)"
echo ""
log "Network config:"
log "  ECS Cluster: $ECS_CLUSTER_ARN"
log "  Task Def:    $TASK_DEF_ARN"
log "  Subnet:      $SUBNET_IDS"
log "  SG:          $SECURITY_GROUP_IDS"
echo ""

confirm "Deploy EventBridge Bronze schedules stack?" && \
run_cmd "Deploying EventBridge Bronze schedules..." \
    aws cloudformation deploy \
        --template-file "${INFRA_DIR}/eventbridge-schedules.yaml" \
        --stack-name prediction-data-schedules \
        --parameter-overrides \
            Environment="$ENV" \
            ECSClusterArn="$ECS_CLUSTER_ARN" \
            TaskDefinitionArn="$TASK_DEF_ARN" \
            SubnetIds="$SUBNET_IDS" \
            SecurityGroupIds="$SECURITY_GROUP_IDS" \
            ScheduleState=ENABLED \
            ScheduleTimezone=America/Chicago \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION" \
        --no-fail-on-empty-changeset

# =========================================================================
# STEP 2: Post-Deployment Verification
# =========================================================================
header "Step 2: Post-Deployment Verification"

# Verify schedules exist
log "Checking Bronze schedules..."
if [ "$DRY_RUN" = false ]; then
    SCHEDULE_COUNT=$(aws scheduler list-schedules \
        --group-name "prediction-data-${ENV}" \
        --region "$AWS_REGION" \
        --query 'length(Schedules)' \
        --output text 2>/dev/null || echo "0")
    if [ "$SCHEDULE_COUNT" -ge 6 ]; then
        log "Bronze schedules: ${SCHEDULE_COUNT} found (expected 6)"
    else
        warn "Bronze schedules: only ${SCHEDULE_COUNT} found (expected 6)"
    fi
fi

log ""
log "Bronze EventBridge schedules:"
if [ "$DRY_RUN" = false ]; then
    aws scheduler list-schedules \
        --group-name "prediction-data-${ENV}" \
        --region "$AWS_REGION" \
        --query 'Schedules[*].[Name,State]' \
        --output table 2>/dev/null || warn "No Bronze schedule group found"
fi

# Run verification script
log ""
log "Running operational verification..."
if [ "$DRY_RUN" = false ]; then
    python "${SCRIPT_DIR}/scripts/verify_bronze_operational.py" 2>/dev/null || true
fi

# =========================================================================
# STEP 3: Trigger Immediate Catchup (Optional)
# =========================================================================
if [ "$SKIP_CATCHUP" = false ]; then
    header "Step 3: Trigger Immediate Catchup"
    log "The schedules will run automatically, but you can trigger an immediate catchup."
    log "This will fetch any missing data since the last successful ingestion."
    echo ""

    if confirm "Trigger immediate Polymarket order_filled catchup?"; then
        if [ "$DRY_RUN" = false ]; then
            log "Running catchup (this may take a few minutes)..."
            python -m prediction_data.cli.main backfill catchup \
                --platform polymarket --entity order_filled 2>&1 | tee -a "$LOG_FILE" || true
        else
            echo -e "  ${YELLOW}[DRY RUN] Would run: prediction-data backfill catchup --platform polymarket --entity order_filled${NC}"
        fi
    fi
fi

# =========================================================================
# Done
# =========================================================================
header "Done"
log "Log saved to: $LOG_FILE"

echo ""
log "Next steps:"
log "  1. Monitor CloudWatch logs: https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#logsV2:log-groups/log-group/\$252Fecs\$252Fprediction-data-prod"
log "  2. Check data freshness: prediction-data status latest"
log "  3. Verify full operational status: python scripts/verify_bronze_operational.py"

if [ "$DRY_RUN" = true ]; then
    warn "This was a dry run. No changes were made."
    log "Re-run without --dry-run to execute."
fi
