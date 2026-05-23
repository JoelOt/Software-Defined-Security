#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Trust Plane: Private Geth PoA (Clique) Node — One-shot startup script.
#
# This script automates the full lifecycle:
#   1. Creates a local sealer account (if none exists)
#   2. Generates genesis.json with the sealer embedded
#   3. Initialises the chain database
#   4. Launches the Geth Docker container
#
# Configuration is loaded from ../.env (see .env.example for defaults).
#
# Usage:  ./start_geth.sh
# Stop:   ./stop_geth.sh   (or docker stop geth-poa && docker rm geth-poa)
# ---------------------------------------------------------------------------
set -euo pipefail

# ── Resolve paths ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
KEYSTORE_DIR="${DATA_DIR}/keystore"
PASSWORD_FILE="${DATA_DIR}/password.txt"
GENESIS_FILE="${DATA_DIR}/genesis.json"

# ── Load .env ──────────────────────────────────────────────────────────────
if [ -f "${PROJECT_ROOT}/.env" ]; then
    # Export all non-comment, non-empty lines
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# ── Configuration (from .env, with sensible defaults) ──────────────────────
CONTAINER_NAME="${GETH_CONTAINER_NAME:-geth-poa}"
DOCKER_IMAGE="${GETH_DOCKER_IMAGE:-ethereum/client-go:v1.13.15}"
NETWORK_ID="${GETH_NETWORK_ID:-12345}"
CHAIN_PERIOD="${GETH_CHAIN_PERIOD:-1}"
ACCOUNT_PASSWORD="${GETH_ACCOUNT_PASSWORD:-testpassword}"
GAS_LIMIT="8000000"

# ── Colours for output ────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No colour

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Pre-flight checks ─────────────────────────────────────────────────────
command -v docker &>/dev/null || err "Docker is not installed or not in PATH."

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    warn "Container '${CONTAINER_NAME}' is already running."
    info "RPC endpoint: http://127.0.0.1:8545"
    info "WS  endpoint: ws://127.0.0.1:8546"
    exit 0
fi

# Remove any stopped container with the same name
docker rm -f "${CONTAINER_NAME}" &>/dev/null || true

# ── Step 1: Create data directory & account ────────────────────────────────
mkdir -p "${DATA_DIR}"
echo -n "${ACCOUNT_PASSWORD}" > "${PASSWORD_FILE}"

if [ -d "${KEYSTORE_DIR}" ] && [ "$(ls -A "${KEYSTORE_DIR}" 2>/dev/null)" ]; then
    info "Existing keystore found. Reusing account."
else
    info "Creating new sealer account..."
    docker run --rm \
        -u "$(id -u):$(id -g)" \
        -e HOME=/data \
        -v "${DATA_DIR}:/data" \
        "${DOCKER_IMAGE}" \
        account new \
        --datadir /data \
        --password /data/password.txt
    ok "Account created."
fi

# Extract the sealer address from the keystore filename
# Keystore files are named like: UTC--2026-05-18T...--<address>
KEYSTORE_FILE=$(ls "${KEYSTORE_DIR}" | head -n 1)
SEALER_ADDRESS=$(echo "${KEYSTORE_FILE}" | grep -oE '[0-9a-f]{40}$')

if [ -z "${SEALER_ADDRESS}" ]; then
    err "Could not extract sealer address from keystore file: ${KEYSTORE_FILE}"
fi

ok "Sealer address: 0x${SEALER_ADDRESS}"

# ── Step 2: Generate genesis.json ──────────────────────────────────────────
# extradata format for Clique:
#   32 bytes vanity (zeros) + 20 bytes sealer address + 65 bytes signature (zeros)
VANITY="0000000000000000000000000000000000000000000000000000000000000000"
SIG_PADDING="0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
EXTRADATA="0x${VANITY}${SEALER_ADDRESS}${SIG_PADDING}"

info "Generating genesis.json (chainId=${NETWORK_ID}, period=${CHAIN_PERIOD}s)..."

cat > "${GENESIS_FILE}" <<EOF
{
  "config": {
    "chainId": ${NETWORK_ID},
    "homesteadBlock": 0,
    "eip150Block": 0,
    "eip155Block": 0,
    "eip158Block": 0,
    "byzantiumBlock": 0,
    "constantinopleBlock": 0,
    "petersburgBlock": 0,
    "istanbulBlock": 0,
    "berlinBlock": 0,
    "londonBlock": 0,
    "clique": {
      "period": ${CHAIN_PERIOD},
      "epoch": 30000
    }
  },
  "difficulty": "1",
  "gasLimit": "${GAS_LIMIT}",
  "extradata": "${EXTRADATA}",
  "alloc": {
    "0x${SEALER_ADDRESS}": {
      "balance": "1000000000000000000000"
    }
  }
}
EOF

ok "genesis.json written to ${GENESIS_FILE}"

# ── Step 3: Initialise the chain database ──────────────────────────────────
# Only initialise if the chaindata directory doesn't exist yet
if [ ! -d "${DATA_DIR}/geth/chaindata" ]; then
    info "Initialising chain database..."
    docker run --rm \
        -u "$(id -u):$(id -g)" \
        -e HOME=/data \
        -v "${DATA_DIR}:/data" \
        "${DOCKER_IMAGE}" \
        init --datadir /data /data/genesis.json
    ok "Chain database initialised."
else
    info "Chain database already exists. Skipping init."
fi

# ── Step 4: Launch the Geth node ───────────────────────────────────────────
info "Starting Geth PoA node in Docker..."

docker run -d \
    --name "${CONTAINER_NAME}" \
    -u "$(id -u):$(id -g)" \
    -e HOME=/data \
    -v "${DATA_DIR}:/data" \
    -p 8545:8545 \
    -p 8546:8546 \
    "${DOCKER_IMAGE}" \
    --datadir /data \
    --networkid "${NETWORK_ID}" \
    --http \
    --http.addr "0.0.0.0" \
    --http.port 8545 \
    --http.api "eth,net,web3,personal,clique" \
    --http.corsdomain "*" \
    --ws \
    --ws.addr "0.0.0.0" \
    --ws.port 8546 \
    --ws.api "eth,net,web3" \
    --ws.origins "*" \
    --allow-insecure-unlock \
    --unlock "0x${SEALER_ADDRESS}" \
    --password /data/password.txt \
    --mine \
    --miner.etherbase "0x${SEALER_ADDRESS}" \
    --nodiscover \
    --verbosity 3

ok "Geth node started in container '${CONTAINER_NAME}'."

# ── Step 5: Health check ───────────────────────────────────────────────────
info "Waiting for RPC to become available..."
for i in $(seq 1 15); do
    if curl -sf -X POST http://127.0.0.1:8545 \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
        &>/dev/null; then
        ok "RPC is live!"
        break
    fi
    sleep 1
    if [ "$i" -eq 15 ]; then
        warn "RPC did not respond after 15s. Check: docker logs ${CONTAINER_NAME}"
    fi
done

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          Geth PoA Node — Running Successfully            ║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  Sealer:    0x${SEALER_ADDRESS}  ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  RPC HTTP:  http://127.0.0.1:8545                       ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  RPC WS:    ws://127.0.0.1:8546                         ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Chain ID:  ${NETWORK_ID}                                       ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Period:    ${CHAIN_PERIOD}s per block                              ${GREEN}║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  Next step: python3 deploy.py                           ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Logs:      docker logs -f ${CONTAINER_NAME}                    ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Stop:      ./stop_geth.sh                              ${GREEN}║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
