#!/usr/bin/env bash
# sync-app.sh -- Sync and restart a single app without full rebuild
# Usage: ./sync-app.sh <appname> [user@host] [remote_path]
#
# App names: ticketmaker, detection_catalog, integration_adoption,
#            integration_catalog, cloud_live, dynaframe

set -euo pipefail

APP_NAME="${1:-}"
REMOTE_HOST="${2:-${REMOTE_HOST:-localhost}}"
REMOTE_PATH="${3:-${REMOTE_PATH:-/opt/dans-world}}"
WORKSPACE="${WORKSPACE:-$HOME/CTOWorkspace}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[sync]${NC} $*"; }
warn() { echo -e "${YELLOW}[sync]${NC} $*"; }
err()  { echo -e "${RED}[sync]${NC} $*" >&2; }

EXCLUDES=(
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='.pytest_cache'
    --exclude='node_modules'
    --exclude='.git'
    --exclude='.DS_Store'
    --exclude='*.duckdb.wal'
    --exclude='venv'
    --exclude='*.log'
)

if [ -z "$APP_NAME" ]; then
    err "Usage: $0 <appname> [user@host] [remote_path]"
    echo ""
    echo "Available apps:"
    echo "  ticketmaker           - Ticket analysis viewer"
    echo "  detection_catalog     - Detection catalog browser"
    echo "  integration_adoption  - Streamlit adoption analytics"
    echo "  integration_catalog   - Integration catalog API"
    echo "  cloud_live            - Aurora Cloud Live dashboard"
    echo "  churn_explorer        - Q3'26 churn analysis dashboards (static)"
    exit 1
fi

is_remote() {
    [[ "$REMOTE_HOST" != "localhost" && "$REMOTE_HOST" != "127.0.0.1" ]]
}

rsync_to() {
    local src="$1"
    local dest="$2"
    shift 2

    if is_remote; then
        rsync -avz --delete "${EXCLUDES[@]}" "$@" "$src" "${REMOTE_HOST}:${REMOTE_PATH}/${dest}"
    else
        rsync -av --delete "${EXCLUDES[@]}" "$@" "$src" "${REMOTE_PATH}/${dest}"
    fi
}

remote_exec() {
    if is_remote; then
        ssh "$REMOTE_HOST" "$@"
    else
        eval "$@"
    fi
}

# Map app name to source directory and extra excludes
case "$APP_NAME" in
    ticketmaker)
        SRC="${WORKSPACE}/02_R_and_D/ticketmaker/"
        EXTRA_EXCLUDES="--exclude=ticket_viewer_env --exclude=uploads --exclude=*.db"
        SUPERVISOR_NAME="ticketmaker"
        ;;
    detection_catalog)
        SRC="${WORKSPACE}/02_R_and_D/detection_catalog/"
        EXTRA_EXCLUDES="--exclude=dcmitre-orig --exclude=detections-code-repo --exclude=enhanced_detections"
        SUPERVISOR_NAME="detection_catalog"
        ;;
    integration_adoption)
        SRC="${WORKSPACE}/03_Product/integration_adoption/analytics/"
        EXTRA_EXCLUDES="--exclude=*.duckdb.wal"
        SUPERVISOR_NAME="integration_adoption"
        ;;
    integration_catalog)
        SRC="${WORKSPACE}/03_Product/integration_catalog/dashboard/backend/"
        EXTRA_EXCLUDES=""
        SUPERVISOR_NAME="integration_catalog"
        ;;
    cloud_live)
        SRC="${WORKSPACE}/02_R_and_D/AW_Point_Products_Demo/aw_managed_cloud_live/"
        EXTRA_EXCLUDES="--exclude=wiz_credentials.json --exclude=wiz_customers.json"
        SUPERVISOR_NAME="cloud_live"
        ;;
    churn_explorer)
        SRC="${WORKSPACE}/scratch/churn_explorer/"
        EXTRA_EXCLUDES="--exclude=__pycache__ --exclude=*.py --exclude=*.csv --exclude=*.xlsx --exclude=*.pdf --exclude=tickets --exclude=tickets_2025 --exclude=tickets_enriched --exclude=customer_profiles --exclude=evidence_docs --exclude=CLAUDE.md --exclude=README.md --exclude=batch_*.json --exclude=full2025_*.json --exclude=rescrape_*.json --exclude=remaining_*.json --exclude=final_rescrape_*.json --exclude=churn_data.json --exclude=churn_data_slim.json --exclude=churn_customers.json --exclude=churn_tickets_*.json --exclude=deep_customer_data.json --exclude=customer_analysis_data.json --exclude=enrich_progress.json --exclude=renewed_clean_sample.json"
        SUPERVISOR_NAME=""
        ;;
    *)
        err "Unknown app: $APP_NAME"
        err "Valid apps: ticketmaker, detection_catalog, integration_adoption, integration_catalog, cloud_live, churn_explorer"
        exit 1
        ;;
esac

if [ ! -d "$SRC" ]; then
    err "Source directory not found: $SRC"
    exit 1
fi

log "Syncing $APP_NAME from $SRC"

if [ -z "$SUPERVISOR_NAME" ]; then
    # Static site -- sync to static-sites/ and no supervisor restart needed
    rsync_to "$SRC" "static-sites/${APP_NAME}/" $EXTRA_EXCLUDES
    log "Done. $APP_NAME synced (static site, no restart needed)."
else
    rsync_to "$SRC" "apps/${APP_NAME}/" $EXTRA_EXCLUDES
    log "Restarting $SUPERVISOR_NAME in apps container..."
    remote_exec "docker exec dw-apps supervisorctl restart ${SUPERVISOR_NAME}"
    log "Checking process status..."
    remote_exec "docker exec dw-apps supervisorctl status ${SUPERVISOR_NAME}"
    log "Done. $APP_NAME synced and restarted."
fi
