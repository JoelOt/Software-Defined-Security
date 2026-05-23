#!/usr/bin/env python3
"""
Trust Plane component: Lightweight helper script to listen to and print 
ThreatIntel smart contract events from Geth in real-time.

Highly useful for debugging and live project demonstrations.
"""
import json
import os
import time
from web3 import Web3

def listen():
    # 1. Connect to Geth RPC
    rpc_url = os.environ.get('DLT_RPC_URL', 'http://127.0.0.1:8545')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print(f"Error: Failed to connect to Geth at {rpc_url}")
        return

    # Inject Geth PoA middleware to validate Clique consensus blocks (longer extraData)
    try:
        from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
    except ImportError:
        from web3.middleware import geth_poa_middleware as poa_middleware
    w3.middleware_onion.inject(poa_middleware, layer=0)

    # 2. Load Contract Data
    base_dir = os.path.dirname(os.path.abspath(__file__))
    contract_data_path = os.path.join(base_dir, 'contract_data.json')
    
    if not os.path.exists(contract_data_path):
        print(f"Error: Contract data file not found at {contract_data_path}. Run deploy.py first.")
        return

    with open(contract_data_path, 'r') as f:
        contract_data = json.load(f)
        
    contract = w3.eth.contract(address=contract_data['address'], abi=contract_data['abi'])
    print(f"Successfully connected to contract: {contract.address}")
    print("=" * 60)
    print("  DLT REAL-TIME EVENT MONITOR  ")
    print("  (Press Ctrl+C to stop)       ")
    print("=" * 60)

    # 3. Create filters starting from block 0 to read history, then stream live
    try:
        # Create event filters looking from block 0 (change to 'latest' to ignore history)
        threat_filter = contract.events.ThreatReported.create_filter(from_block=0)
        status_filter = contract.events.StatusUpdated.create_filter(from_block=0)
    except TypeError:
        threat_filter = contract.events.ThreatReported.create_filter(fromBlock=0)
        status_filter = contract.events.StatusUpdated.create_filter(fromBlock=0)

    # Helper function to print events nicely
    def print_event_info(event_name, event):
        tx_hash = event['transactionHash'].hex()
        block_num = event['blockNumber']
        args = event['args']
        
        # Format printing
        print(f"\n🟢 [{time.strftime('%Y-%m-%d %H:%M:%S')}] EVENT: {event_name}")
        print(f"   Block Number:    #{block_num}")
        print(f"   Transaction:     0x{tx_hash}")
             # Enum mapping for status fields
        status_mapping = {0: "NONE", 1: "PENDING", 2: "QUARANTINED"}
        
        print("   Arguments:")
        for key, val in args.items():
            if key in ('newStatus', 'status') and val in status_mapping:
                print(f"     - {key}: {status_mapping[val]} ({val})")
            else:
                print(f"     - {key}: {val}")
        print("-" * 60)

    # 4. Stream and print events
    try:
        # Dump historical entries first
        historical_threats = threat_filter.get_all_entries()
        historical_status = status_filter.get_all_entries()
        
        # Sort history by block number
        all_historical = []
        for e in historical_threats:
            all_historical.append(("ThreatReported", e))
        for e in historical_status:
            all_historical.append(("StatusUpdated", e))
        all_historical.sort(key=lambda x: x[1]['blockNumber'])
        
        if all_historical:
            print(f"--- Printing historical DLT events ({len(all_historical)} found) ---")
            for name, event in all_historical:
                print_event_info(name, event)
            print("--- End of History. Listening for live events... ---")
        else:
            print("No historical events found. Listening for live events...")

        # Poll loop for live events
        while True:
            for event in threat_filter.get_new_entries():
                print_event_info("ThreatReported", event)
            for event in status_filter.get_new_entries():
                print_event_info("StatusUpdated", event)
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping DLT monitor.")

if __name__ == "__main__":
    listen()
