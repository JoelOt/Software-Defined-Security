#!/bin/bash

# -----------------------------------------------------------------------------
# Federated SDN Project: GRE Tunnel Setup Script
# Architecture: Data Plane
# Description: Connects the local Mininet OVS instance to a remote OVS instance 
#              via a GRE tunnel to establish the federated network.
# -----------------------------------------------------------------------------

set -e

# Basic error handling for arguments
if [ "$#" -ne 3 ]; then
    echo "Error: Incorrect number of arguments."
    echo "Usage: $0 <LOCAL_VM_IP> <REMOTE_VM_IP> <OVS_SWITCH_NAME>"
    echo "Example: $0 192.168.1.10 192.168.1.11 s1"
    exit 1
fi

LOCAL_VM_IP=$1
REMOTE_VM_IP=$2
OVS_SWITCH_NAME=$3
TUNNEL_NAME="gre-$OVS_SWITCH_NAME"

echo "=========================================="
echo " Initiating Federated GRE Tunnel Setup"
echo "=========================================="
echo "Local VM IP:    $LOCAL_VM_IP"
echo "Remote VM IP:   $REMOTE_VM_IP"
echo "OVS Switch:     $OVS_SWITCH_NAME"
echo "Tunnel Name:    $TUNNEL_NAME"
echo "=========================================="

# Check if the OVS switch exists
if ! ovs-vsctl list-br | grep -q -w "$OVS_SWITCH_NAME"; then
    echo "Error: Open vSwitch '$OVS_SWITCH_NAME' does not exist. Please create the Mininet topology first."
    exit 1
fi

echo "[*] Checking for existing tunnel interface '$TUNNEL_NAME'..."
# Clean up existing tunnel with the same name if it exists
if ip link show "$TUNNEL_NAME" > /dev/null 2>&1; then
    echo "[!] Tunnel interface '$TUNNEL_NAME' already exists. Recreating..."
    ip link set "$TUNNEL_NAME" down
    ip tunnel del "$TUNNEL_NAME"
fi

# Clean up port from OVS if it exists
if ovs-vsctl list-ports "$OVS_SWITCH_NAME" | grep -q -w "$TUNNEL_NAME"; then
    echo "[!] Removing existing port '$TUNNEL_NAME' from Open vSwitch '$OVS_SWITCH_NAME'..."
    ovs-vsctl del-port "$OVS_SWITCH_NAME" "$TUNNEL_NAME"
fi

echo "[*] Creating GRE tunnel interface '$TUNNEL_NAME' from $LOCAL_VM_IP to $REMOTE_VM_IP..."
# 3. Create a GRE tunnel interface bridging the local host to the remote host
ip tunnel add "$TUNNEL_NAME" mode gre remote "$REMOTE_VM_IP" local "$LOCAL_VM_IP" ttl 255

echo "[*] Bringing up the GRE tunnel interface '$TUNNEL_NAME'..."
ip link set "$TUNNEL_NAME" up

echo "[*] Attaching GRE tunnel interface '$TUNNEL_NAME' to Open vSwitch '$OVS_SWITCH_NAME'..."
# 4. Attach the GRE interface to the specified Open vSwitch
ovs-vsctl add-port "$OVS_SWITCH_NAME" "$TUNNEL_NAME"

echo "[+] Successfully established GRE tunnel and attached it to $OVS_SWITCH_NAME."
echo "=========================================="
