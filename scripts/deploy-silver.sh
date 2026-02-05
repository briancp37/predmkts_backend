#!/usr/bin/env bash
# =============================================================================
# Silver Release 02 - Remaining Deployment Steps
#
# Only includes what's NOT already deployed:
#   Step 1: Update CloudWatch monitoring (add Silver metric filters + alarms)
#   Step 2: Deploy EventBridge Silver schedules (near-continuous automation)
#   Step 3: Post-deployment verification
#
# Already deployed (not included):
#   - S3 Silver bucket (prediction-silver-bucket stack, CREATE_COMPLETE)
#   - Glue Catalog (silver_polymarket, silver_kalshi namespaces)
#   - IAM roles (prediction-data-iam-roles stack)
#   - ECS cluster (prediction-data-ecs stack)
#   - All 6 Iceberg tables (created, populated: 400M trades, 387K markets, 182K events)
#   - Bronze EventBridge schedules (prediction-data-schedules stack)
#
# Usage:
#   ./scripts/deploy-silver.sh              # Run all steps interactively
#   ./scripts/deploy-silver.sh --dry-run    # Preview without executing
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
ECS_CLUSTER_NAME="prediction-data-prod"
ALERT_EMAIL="briancp32@gmail.com"

# --- Internal state ---
DRY_RUN=false
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="${SCRIPT_DIR}/infrastructure"
LOG_FILE="/tmp/deploy-silver-$(date +%Y%m%d-%H%M%S).log"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --help)
            echo "Usage: $0 [--dry-run]"
            echo ""
            echo "Steps:"
            echo "  1  Update CloudWatch monitoring (add Silver metric filters + alarms)"
            echo "  2  Deploy EventBridge Silver schedules"
            echo "  3  Post-deployment verification"
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
header "Silver Release 02 - Remaining Deployment"
log "Environment: $ENV"
log "Region: $AWS_REGION"
log "Dry Run: $DRY_RUN"
log "Log file: $LOG_FILE"
echo ""

if ! aws sts get-caller-identity --region "$AWS_REGION" &>/dev/null; then
    err "AWS credentials not configured."
    exit 1
fi
log "AWS Account: $(aws sts get-caller-identity --query Account --output text)"

# =========================================================================
# STEP 1: Update CloudWatch Monitoring
# =========================================================================
header "Step 1: Update CloudWatch Monitoring"
log "The current monitoring stack (deployed 2026-01-28) is missing Silver-specific resources:"
log "  - 4 metric filters: SilverProcessingSuccess, SilverNoOp, SilverConcurrencySkip, SilverProcessingFailure"
log "  - 2 alarms: SilverTradesMissingRuns, SilverProcessingErrors"
log "  - 2 dashboard panels: Silver Runs by Outcome, Silver Concurrency Skip Rate"
echo ""

confirm "Update CloudWatch monitoring stack with Silver metrics?" && \
run_cmd "Updating CloudWatch monitoring stack..." \
    aws cloudformation deploy \
        --template-file "${INFRA_DIR}/cloudwatch-monitoring.yaml" \
        --stack-name prediction-data-monitoring \
        --parameter-overrides \
            Environment="$ENV" \
            LogGroupName="$LOG_GROUP_NAME" \
            ECSClusterName="$ECS_CLUSTER_NAME" \
            AlertEmail="$ALERT_EMAIL" \
        --region "$AWS_REGION" \
        --no-fail-on-empty-changeset

# =========================================================================
# STEP 2: Deploy EventBridge Silver Schedules
# =========================================================================
header "Step 2: Deploy EventBridge Silver Schedules"
log "This creates a NEW CloudFormation stack with 11 EventBridge schedules:"
log "  ENABLED:"
log "    - silver-polymarket-trades-prod     (every 10 min)"
log "    - silver-polymarket-markets-prod    (every 30 min)"
log "    - silver-polymarket-events-prod     (every 30 min)"
log "    - silver-maintain-compact-prod      (daily 04:00 UTC)"
log "    - silver-maintain-full-prod         (weekly Sunday 04:00 UTC)"
log "  DISABLED (Kalshi scaffold):"
log "    - silver-kalshi-trades-prod"
log "    - silver-kalshi-markets-prod"
log "    - silver-kalshi-events-prod"
echo ""
log "Network config (from existing Bronze schedules):"
log "  ECS Cluster: $ECS_CLUSTER_ARN"
log "  Task Def:    $TASK_DEF_ARN"
log "  Subnet:      $SUBNET_IDS"
log "  SG:          $SECURITY_GROUP_IDS"
echo ""

confirm "Deploy EventBridge Silver schedules stack?" && \
run_cmd "Deploying EventBridge Silver schedules..." \
    aws cloudformation deploy \
        --template-file "${INFRA_DIR}/eventbridge-silver-schedules.yaml" \
        --stack-name prediction-data-silver-schedules \
        --parameter-overrides \
            Environment="$ENV" \
            ECSClusterArn="$ECS_CLUSTER_ARN" \
            TaskDefinitionArn="$TASK_DEF_ARN" \
            SubnetIds="$SUBNET_IDS" \
            SecurityGroupIds="$SECURITY_GROUP_IDS" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION" \
        --no-fail-on-empty-changeset

# =========================================================================
# STEP 3: Post-Deployment Verification
# =========================================================================
header "Step 3: Post-Deployment Verification"

# Verify Silver metric filters were created
log "Checking Silver metric filters..."
if [ "$DRY_RUN" = false ]; then
    FILTER_COUNT=$(aws logs describe-metric-filters \
        --log-group-name "$LOG_GROUP_NAME" \
        --region "$AWS_REGION" \
        --query 'metricFilters[?contains(filterName, `Silver`)].filterName' \
        --output text 2>/dev/null | wc -w | tr -d ' ')
    if [ "$FILTER_COUNT" -ge 4 ]; then
        log "Silver metric filters: ${FILTER_COUNT} found (expected 4)"
    else
        warn "Silver metric filters: only ${FILTER_COUNT} found (expected 4)"
    fi
fi

# Verify Silver alarms
log ""
log "Silver alarm states:"
if [ "$DRY_RUN" = false ]; then
    aws cloudwatch describe-alarms \
        --alarm-name-prefix "prediction-data-silver" \
        --region "$AWS_REGION" \
        --query 'MetricAlarms[*].[AlarmName,StateValue]' \
        --output table 2>/dev/null || warn "No Silver alarms found"
fi

# Verify Silver schedules
log ""
log "Silver EventBridge schedules:"
if [ "$DRY_RUN" = false ]; then
    aws scheduler list-schedules \
        --group-name "prediction-data-silver-${ENV}" \
        --region "$AWS_REGION" \
        --query 'Schedules[*].[Name,State]' \
        --output table 2>/dev/null || warn "No Silver schedule group found"
fi

# Check for first Silver ECS task run (may not exist yet)
log ""
log "Recent Silver ECS tasks (if any):"
if [ "$DRY_RUN" = false ]; then
    aws logs filter-log-events \
        --log-group-name "$LOG_GROUP_NAME" \
        --start-time "$(date -u -v-30M +%s000 2>/dev/null || date -u -d '30 minutes ago' +%s000)" \
        --filter-pattern '"silver"' \
        --limit 5 \
        --region "$AWS_REGION" \
        --query 'events[*].message' \
        --output text 2>/dev/null || log "No Silver logs yet (first run should appear within 10 minutes)"
fi

echo ""
header "24-Hour Monitoring Checklist"
log "CloudWatch dashboard:"
log "  https://${AWS_REGION}.console.aws.amazon.com/cloudwatch/home?region=${AWS_REGION}#dashboards/dashboard/prediction-data-${ENV}"
echo ""
log "Verify after 24 hours:"
log "  [ ] SilverProcessingSuccess > 0  (at least some runs process new data)"
log "  [ ] SilverNoOp > 50%             (most runs find no new data - expected)"
log "  [ ] SilverConcurrencySkip < 10%  (minimal overlap between runs)"
log "  [ ] SilverProcessingFailure = 0  (zero sustained failures)"
log "  [ ] Both Silver alarms in OK state"
log "  [ ] ECS cost < \$2/day for 0.25vCPU/512MB tasks"

# =========================================================================
# Done
# =========================================================================
header "Done"
log "Log saved to: $LOG_FILE"
if [ "$DRY_RUN" = true ]; then
    warn "This was a dry run. No changes were made."
    log "Re-run without --dry-run to execute."
fi
