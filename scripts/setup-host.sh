#!/usr/bin/env bash
# setup-host.sh -- One-time setup for Ubuntu 22.04 Proxmox VM
# Run this ON the VM as root or with sudo.
# Installs Docker, Docker Compose v2, Node.js 20, and prepares the directory.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[setup]${NC} $*"; }
err() { echo -e "${RED}[setup]${NC} $*" >&2; }

if [ "$(id -u)" -ne 0 ]; then
    err "Run this script as root (sudo ./setup-host.sh)"
    exit 1
fi

log "Updating system packages..."
apt-get update && apt-get upgrade -y

# ---------------------------------------------------------------
# Docker Engine
# ---------------------------------------------------------------
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    log "Docker installed."
else
    log "Docker already installed."
fi

# Add current user to docker group (if not root)
REAL_USER="${SUDO_USER:-$USER}"
if [ "$REAL_USER" != "root" ]; then
    usermod -aG docker "$REAL_USER"
    log "Added $REAL_USER to docker group (re-login to take effect)."
fi

# ---------------------------------------------------------------
# Node.js 20 LTS (for building frontend assets)
# ---------------------------------------------------------------
if ! command -v node &>/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]; then
    log "Installing Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
    log "Node.js $(node -v) installed."
else
    log "Node.js $(node -v) already installed."
fi

# ---------------------------------------------------------------
# Create project directory
# ---------------------------------------------------------------
INSTALL_DIR="/opt/dans-world"
log "Creating ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"/{apps,gateway/conf.d,admin/{templates,static},static-sites,html-dropzone,scripts,apps/integration_catalog_dist}

# Set ownership to the deploying user
if [ "$REAL_USER" != "root" ]; then
    chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"
fi

# ---------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------
if command -v ufw &>/dev/null; then
    log "Configuring firewall..."
    ufw allow 22/tcp    # SSH
    ufw allow 80/tcp    # HTTP
    ufw allow 443/tcp   # HTTPS
    ufw --force enable
    log "Firewall configured (SSH, HTTP, HTTPS allowed)."
fi

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
echo ""
log "============================================"
log "  Host setup complete!"
log "============================================"
log ""
log "  Docker:  $(docker --version)"
log "  Compose: $(docker compose version)"
log "  Node.js: $(node -v)"
log "  Path:    ${INSTALL_DIR}"
log ""
log "  Next steps:"
log "  1. From your Mac, run: ./deploy.sh ${REAL_USER}@$(hostname -I | awk '{print $1}')"
log "  2. Edit ${INSTALL_DIR}/.env with a real AUTH_SECRET and ADMIN_PASSWORD"
log "  3. Access at http://$(hostname -I | awk '{print $1}')"
log ""
