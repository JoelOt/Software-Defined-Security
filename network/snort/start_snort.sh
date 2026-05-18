#!/bin/bash

# -----------------------------------------------------------------------------
# Federated SDN Project: Snort VNF Launcher
# Architecture: Data Plane (Security VNF)
# Description: Auto-detects installed Snort version (v2 or v3) and launches
#              the correct configuration on the OVS dummy interface.
# Usage: sudo ./start_snort.sh <SWITCH_NAME>
# Example: sudo ./start_snort.sh sa1
# -----------------------------------------------------------------------------

set -e

SWITCH_NAME="${1:-s1}"
SNORT_INTF="${SWITCH_NAME}-snort"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"

# Ensure the log directory exists
mkdir -p "$LOG_DIR"

# Verify that the Snort interface exists
if ! ip link show "$SNORT_INTF" > /dev/null 2>&1; then
    echo "[!] Error: Interface '$SNORT_INTF' does not exist."
    echo "    Make sure the Mininet topology is running first."
    echo "    Expected interface created by: topology_setup.py --domain-code ${SWITCH_NAME%1}"
    exit 1
fi

echo "=========================================="
echo " Snort VNF Launcher"
echo "=========================================="
echo "Switch:    $SWITCH_NAME"
echo "Interface: $SNORT_INTF"
echo "Log Dir:   $LOG_DIR"

# Detect Snort version
SNORT_VERSION_OUTPUT=$(snort --version 2>&1 || true)

if echo "$SNORT_VERSION_OUTPUT" | grep -q "Snort\+\+"; then
    # ---- Snort 3.x detected ----
    SNORT_MAJOR=3
    echo "Detected:  Snort 3 (Snort++)"
    echo "Config:    snort.lua"
    echo "=========================================="

    snort -c "${SCRIPT_DIR}/snort.lua" \
          -i "$SNORT_INTF" \
          -l "$LOG_DIR" \
          -A fast

elif echo "$SNORT_VERSION_OUTPUT" | grep -qE "Version [2]\.[0-9]"; then
    # ---- Snort 2.x detected ----
    SNORT_MAJOR=2
    echo "Detected:  Snort 2.x"
    echo "Config:    snort.conf"
    echo "=========================================="

    snort -c "${SCRIPT_DIR}/snort.conf" \
          -i "$SNORT_INTF" \
          -l "$LOG_DIR" \
          -A fast \
          -Q

else
    echo "[!] Error: Could not detect Snort version."
    echo "    Output was: $SNORT_VERSION_OUTPUT"
    echo "    Please install Snort 2.x or Snort 3.x."
    exit 1
fi
