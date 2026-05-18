#!/bin/bash

# Absolute path to iptables
IPTABLES="/usr/sbin/iptables"

# Flush existing iptables rules
$IPTABLES -F

# Default policy to drop all incoming and forwarded packets
$IPTABLES -P INPUT DROP
$IPTABLES -P FORWARD DROP

# Allow established and related incoming connections
$IPTABLES -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow loopback access
$IPTABLES -A INPUT -i lo -j ACCEPT

# Function to add rules for a specific IP
add_ip_rules() {
    local ip=$1

    $IPTABLES -A INPUT -p tcp -s $ip -j ACCEPT
    $IPTABLES -A INPUT -p udp -s $ip -j ACCEPT
}

# Add rules for each IP
add_ip_rules $BOOTNODE_IP
add_ip_rules $IP_NODE_1
add_ip_rules $IP_NODE_2
add_ip_rules $IP_NODE_3
add_ip_rules $IP_NODE_4
add_ip_rules $IP_PROXY
add_ip_rules $IP_MLFO

echo "Firewall rules set up successfully."
