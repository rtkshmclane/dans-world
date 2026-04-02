#!/usr/bin/env bash
# deploy.sh -- Full sync from CTOWorkspace to Docker host + rebuild
# Usage: ./deploy.sh [user@host] [remote_path]
#
# Defaults:
#   REMOTE_HOST: localhost (set via env or arg)
#   REMOTE_PATH: /opt/dans-world

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORKSPACE="${WORKSPACE:-$HOME/CTOWorkspace}"

REMOTE_HOST="${1:-${REMOTE_HOST:-localhost}}"
REMOTE_PATH="${2:-${REMOTE_PATH:-/opt/dans-world}}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*" >&2; }

# Common rsync excludes
EXCLUDES=(
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='.pytest_cache'
    --exclude='node_modules'
    --exclude='.git'
    --exclude='.DS_Store'
    --exclude='*.duckdb.wal'
    --exclude='venv'
    --exclude='ticket_viewer_env'
    --exclude='.env'
    --exclude='*.log'
)

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

# ---------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------
log "Starting full deploy to ${REMOTE_HOST}:${REMOTE_PATH}"

if is_remote; then
    log "Testing SSH connection..."
    ssh -q -o ConnectTimeout=5 "$REMOTE_HOST" exit || { err "Cannot SSH to $REMOTE_HOST"; exit 1; }
fi

# Ensure remote directory structure
remote_exec "mkdir -p ${REMOTE_PATH}/{apps,gateway/conf.d,admin/{templates,static},static-sites,html-dropzone,scripts,apps/integration_catalog_dist}"

# ---------------------------------------------------------------
# Sync infrastructure (Dockerfiles, configs, compose)
# ---------------------------------------------------------------
log "Syncing infrastructure files..."
rsync_to "${PROJECT_DIR}/docker-compose.yml" ""
rsync_to "${PROJECT_DIR}/gateway/" "gateway/"
rsync_to "${PROJECT_DIR}/admin/" "admin/"
rsync_to "${PROJECT_DIR}/apps/Dockerfile" "apps/"
rsync_to "${PROJECT_DIR}/apps/supervisord.conf" "apps/"
rsync_to "${PROJECT_DIR}/apps/requirements.txt" "apps/"
rsync_to "${PROJECT_DIR}/scripts/" "scripts/"
rsync_to "${PROJECT_DIR}/html-dropzone/" "html-dropzone/"

# Copy .env.example if .env doesn't exist
remote_exec "test -f ${REMOTE_PATH}/.env || cp ${REMOTE_PATH}/.env.example ${REMOTE_PATH}/.env 2>/dev/null || true"
if is_remote; then
    rsync -avz "${PROJECT_DIR}/.env.example" "${REMOTE_HOST}:${REMOTE_PATH}/.env.example"
else
    rsync -av "${PROJECT_DIR}/.env.example" "${REMOTE_PATH}/.env.example"
fi

# ---------------------------------------------------------------
# Sync Python apps from CTOWorkspace
# ---------------------------------------------------------------
log "Syncing Ticketmaker..."
rsync_to "${WORKSPACE}/02_R_and_D/ticketmaker/" "apps/ticketmaker/" \
    --exclude='ticket_viewer_env' \
    --exclude='uploads' \
    --exclude='*.db'

log "Syncing Detection Catalog..."
rsync_to "${WORKSPACE}/02_R_and_D/detection_catalog/" "apps/detection_catalog/" \
    --exclude='dcmitre-orig' \
    --exclude='detections-code-repo' \
    --exclude='enhanced_detections'

log "Syncing Integration Adoption..."
rsync_to "${WORKSPACE}/03_Product/integration_adoption/analytics/" "apps/integration_adoption/" \
    --exclude='*.duckdb.wal'

log "Syncing Integration Catalog Backend..."
rsync_to "${WORKSPACE}/03_Product/integration_catalog/dashboard/backend/" "apps/integration_catalog/"

log "Syncing Aurora Cloud Live..."
rsync_to "${WORKSPACE}/02_R_and_D/AW_Point_Products_Demo/aw_managed_cloud_live/" "apps/cloud_live/" \
    --exclude='wiz_credentials.json' \
    --exclude='wiz_customers.json'

# ---------------------------------------------------------------
# Sync static demo sites
# ---------------------------------------------------------------
log "Syncing static demo sites..."

rsync_to "${WORKSPACE}/02_R_and_D/AW_Point_Products_Demo/" "static-sites/AW_Point_Products_Demo/" \
    --exclude='aw_managed_cloud_live' \
    --exclude='*.py' \
    --exclude='requirements.txt'

if [ -d "${WORKSPACE}/02_R_and_D/rsac_agentic_demo_v3" ]; then
    rsync_to "${WORKSPACE}/02_R_and_D/rsac_agentic_demo_v3/" "static-sites/rsac_agentic_demo_v3/"
fi

if [ -d "${WORKSPACE}/02_R_and_D/rsac_demo_wherewolf" ]; then
    rsync_to "${WORKSPACE}/02_R_and_D/rsac_demo_wherewolf/" "static-sites/rsac_demo_wherewolf/"
fi

# Compliance reporting -- check multiple possible locations
for dir in "${WORKSPACE}/05_Service_Delivery/compliance_reporting" "${WORKSPACE}/02_R_and_D/compliance_reporting"; do
    if [ -d "$dir" ]; then
        rsync_to "$dir/" "static-sites/compliance_reporting/"
        break
    fi
done

log "Syncing Churn Explorer..."
rsync_to "${WORKSPACE}/scratch/churn_explorer/" "static-sites/churn_explorer/" \
    --exclude='__pycache__' \
    --exclude='*.py' \
    --exclude='*.csv' \
    --exclude='*.xlsx' \
    --exclude='*.pdf' \
    --exclude='tickets' \
    --exclude='tickets_2025' \
    --exclude='tickets_enriched' \
    --exclude='customer_profiles' \
    --exclude='evidence_docs' \
    --exclude='CLAUDE.md' \
    --exclude='README.md' \
    --exclude='*.log' \
    --include='*.html' \
    --include='*.json' \
    --exclude='batch_*.json' \
    --exclude='full2025_*.json' \
    --exclude='rescrape_*.json' \
    --exclude='remaining_*.json' \
    --exclude='final_rescrape_*.json' \
    --exclude='churn_data.json' \
    --exclude='churn_data_slim.json' \
    --exclude='churn_customers.json' \
    --exclude='churn_tickets_*.json' \
    --exclude='deep_customer_data.json' \
    --exclude='customer_analysis_data.json' \
    --exclude='enrich_progress.json' \
    --exclude='renewed_clean_sample.json'

# ---------------------------------------------------------------
# Build Integration Catalog frontend (if source exists)
# ---------------------------------------------------------------
CATALOG_FRONTEND="${WORKSPACE}/03_Product/integration_catalog/dashboard/frontend"
if [ -d "$CATALOG_FRONTEND" ] && [ -f "$CATALOG_FRONTEND/package.json" ]; then
    log "Building Integration Catalog frontend..."
    (
        cd "$CATALOG_FRONTEND"
        npm install --production=false 2>/dev/null || warn "npm install failed -- skipping frontend build"
        npm run build 2>/dev/null && {
            rsync_to "$CATALOG_FRONTEND/dist/" "apps/integration_catalog_dist/"
            log "Frontend build synced."
        } || warn "Frontend build failed -- skipping"
    )
else
    warn "Integration Catalog frontend not found -- skipping build"
fi

# ---------------------------------------------------------------
# Docker build + up
# ---------------------------------------------------------------
log "Building and starting containers..."
remote_exec "cd ${REMOTE_PATH} && docker compose build && docker compose up -d"

log "Waiting for containers to start..."
sleep 5

remote_exec "cd ${REMOTE_PATH} && docker compose ps"

log "Deploy complete."
log "Access the app at: http://${REMOTE_HOST}"
log "Default login: admin / (check .env ADMIN_PASSWORD)"
