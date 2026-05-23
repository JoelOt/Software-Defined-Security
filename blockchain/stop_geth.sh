#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Trust Plane: Stop and optionally clean the private Geth PoA node.
#
# Configuration is loaded from ../.env (see .env.example for defaults).
#
# Usage:
#   ./stop_geth.sh          # Stop the container (preserves chain data)
#   ./stop_geth.sh --clean  # Stop AND delete all chain data (full reset)
# ---------------------------------------------------------------------------
set -euo pipefail

# ── Resolve paths ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"

# ── Load .env ──────────────────────────────────────────────────────────────
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

CONTAINER_NAME="${GETH_CONTAINER_NAME:-geth-poa}"

# ── Colours ────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

# ── Stop and remove the container ──────────────────────────────────────────
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    info "Stopping container '${CONTAINER_NAME}'..."
    docker stop "${CONTAINER_NAME}" &>/dev/null || true
    docker rm "${CONTAINER_NAME}" &>/dev/null || true
    ok "Container stopped and removed."
else
    warn "Container '${CONTAINER_NAME}' is not running."
fi

# ── If --clean flag is passed, wipe all chain data ─────────────────────────
if [[ "${1:-}" == "--clean" ]]; then
    if [ -d "${DATA_DIR}" ]; then
        warn "Deleting all chain data at ${DATA_DIR}..."
        rm -rf "${DATA_DIR}"
        ok "Chain data wiped. Run ./start_geth.sh to create a fresh chain."
    else
        info "No data directory found. Nothing to clean."
    fi
fi
