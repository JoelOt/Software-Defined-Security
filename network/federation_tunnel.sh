#!/bin/bash

# -----------------------------------------------------------------------------
# Federated SDN Project: Federation Tunnel Setup Script
# Architecture: Data Plane
# Description: Connects the local Mininet OVS instance to a remote OVS instance 
#              via a GRE tunnel, OR creates a local patch port if both domains 
#              are on the same VM.
# -----------------------------------------------------------------------------

set -e

# Basic error handling for arguments
if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    echo "Error: Incorrect number of arguments."
    echo "Usage (Different VMs): $0 <LOCAL_VM_IP> <REMOTE_VM_IP> <LOCAL_OVS_SWITCH>"
    echo "Usage (Same VM):       $0 <LOCAL_VM_IP> <LOCAL_VM_IP> <LOCAL_OVS_SWITCH> <REMOTE_OVS_SWITCH>"
    echo "Example (GRE):   $0 192.168.1.10 192.168.1.11 sa"
    echo "Example (Patch): $0 127.0.0.1 127.0.0.1 sa sb"
    exit 1
fi

LOCAL_VM_IP=$1
REMOTE_VM_IP=$2
LOCAL_OVS_SWITCH=$3
REMOTE_OVS_SWITCH=$4

echo "=========================================="
echo " Initiating Federation Tunnel Setup"
echo "=========================================="
echo "Local VM IP:      $LOCAL_VM_IP"
echo "Remote VM IP:     $REMOTE_VM_IP"
echo "Local OVS Switch: $LOCAL_OVS_SWITCH"

if [ "$LOCAL_VM_IP" == "$REMOTE_VM_IP" ]; then
    # Same VM scenario - use patch ports
    echo "Mode:             Local Patch Port"
    if [ -z "$REMOTE_OVS_SWITCH" ]; then
        echo "=========================================="
        echo "Error: For same-VM setup, please provide the remote OVS switch name as the 4th argument."
        echo "Example: $0 $LOCAL_VM_IP $LOCAL_VM_IP $LOCAL_OVS_SWITCH sb"
        exit 1
    fi
    echo "Remote OVS Switch: $REMOTE_OVS_SWITCH"
    echo "=========================================="

    # Check if switches exist
    for SWITCH in "$LOCAL_OVS_SWITCH" "$REMOTE_OVS_SWITCH"; do
        if ! ovs-vsctl list-br | grep -q -w "$SWITCH"; then
            echo "Error: Open vSwitch '$SWITCH' does not exist. Please create the Mininet topology first."
            exit 1
        fi
    done

    PATCH_LOCAL="patch-$REMOTE_OVS_SWITCH"
    PATCH_REMOTE="patch-$LOCAL_OVS_SWITCH"

    echo "[*] Cleaning up existing patch ports if any..."
    ovs-vsctl --if-exists del-port "$LOCAL_OVS_SWITCH" "$PATCH_LOCAL"
    ovs-vsctl --if-exists del-port "$REMOTE_OVS_SWITCH" "$PATCH_REMOTE"

    echo "[*] Creating patch port on '$LOCAL_OVS_SWITCH' connected to '$REMOTE_OVS_SWITCH'..."
    ovs-vsctl add-port "$LOCAL_OVS_SWITCH" "$PATCH_LOCAL" -- set interface "$PATCH_LOCAL" type=patch options:peer="$PATCH_REMOTE"

    echo "[*] Creating patch port on '$REMOTE_OVS_SWITCH' connected to '$LOCAL_OVS_SWITCH'..."
    ovs-vsctl add-port "$REMOTE_OVS_SWITCH" "$PATCH_REMOTE" -- set interface "$PATCH_REMOTE" type=patch options:peer="$PATCH_LOCAL"

    echo "[+] Successfully established patch cable between $LOCAL_OVS_SWITCH and $REMOTE_OVS_SWITCH."
    echo "[!] Note: Patch port setup is bidirectional. You only need to run this script once!"
    echo "=========================================="

else
    # Different VM scenario - use GRE tunnel
    echo "Mode:             GRE Tunnel"
    echo "=========================================="
    
    TUNNEL_NAME="gre-$LOCAL_OVS_SWITCH"

    if ! ovs-vsctl list-br | grep -q -w "$LOCAL_OVS_SWITCH"; then
        echo "Error: Open vSwitch '$LOCAL_OVS_SWITCH' does not exist. Please create the Mininet topology first."
        exit 1
    fi

    echo "[*] Checking for existing tunnel interface '$TUNNEL_NAME'..."
    if ip link show "$TUNNEL_NAME" > /dev/null 2>&1; then
        echo "[!] Tunnel interface '$TUNNEL_NAME' already exists. Recreating..."
        ip link set "$TUNNEL_NAME" down
        ip tunnel del "$TUNNEL_NAME"
    fi

    if ovs-vsctl list-ports "$LOCAL_OVS_SWITCH" | grep -q -w "$TUNNEL_NAME"; then
        echo "[!] Removing existing port '$TUNNEL_NAME' from Open vSwitch '$LOCAL_OVS_SWITCH'..."
        ovs-vsctl del-port "$LOCAL_OVS_SWITCH" "$TUNNEL_NAME"
    fi

    echo "[*] Creating GRE tunnel interface '$TUNNEL_NAME' from $LOCAL_VM_IP to $REMOTE_VM_IP..."
    ip tunnel add "$TUNNEL_NAME" mode gre remote "$REMOTE_VM_IP" local "$LOCAL_VM_IP" ttl 255

    echo "[*] Bringing up the GRE tunnel interface '$TUNNEL_NAME'..."
    ip link set "$TUNNEL_NAME" up

    echo "[*] Attaching GRE tunnel interface '$TUNNEL_NAME' to Open vSwitch '$LOCAL_OVS_SWITCH'..."
    ovs-vsctl add-port "$LOCAL_OVS_SWITCH" "$TUNNEL_NAME"

    echo "[+] Successfully established GRE tunnel and attached it to $LOCAL_OVS_SWITCH."
    echo "=========================================="
fi
