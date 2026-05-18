"""
Trust Plane component: Smart Contract deployment script for the federated SDN architecture.
"""
import json
import os
import time
from web3 import Web3
from solcx import compile_source, install_solc
from dotenv import load_dotenv

def deploy_contract():
    load_dotenv()
    # 1. Connect to local Geth RPC
    rpc_url = os.environ.get('DLT_RPC_URL', 'http://geth-node1:8545')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    # Wait for Geth to be ready (useful for Docker Compose start-up)
    max_retries = 10
    for i in range(max_retries):
        if w3.is_connected():
            break
        print(f"Waiting for Geth node at {rpc_url} (Attempt {i+1}/{max_retries})...")
        time.sleep(5)
    else:
        print(f"Error: Could not connect to Geth at {rpc_url} after {max_retries} attempts.")
        return

    # Use the Chain ID from your genesis config (12345)
    chain_id = int(os.environ.get('CHAIN_ID', 12345))
    
    # Inject PoA middleware for Geth PoA networks
    from web3.middleware import geth_poa_middleware
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    print("Successfully connected to Ethereum node.")
    
    # 2. Setup Account (Prefer private key from env for Docker environments)
    private_key = os.environ.get('PRIVATE_KEY')
    
    if private_key and not private_key.startswith('0x'):
        private_key = '0x' + private_key

    if private_key:
        account = w3.eth.account.from_key(private_key)
        deployer_address = account.address
    else:
        if len(w3.eth.accounts) == 0:
            print("Error: No accounts found and no PRIVATE_KEY provided.")
            return
        deployer_address = w3.eth.accounts[0]

    print(f"Using deployer account: {deployer_address}")

    # Set up file paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    contract_file = os.path.join(base_dir, 'ThreatIntel.sol')
    output_file = os.path.join(base_dir, 'contract_data.json')

    # Read the contract source
    with open(contract_file, 'r') as f:
        contract_source = f.read()

    # Install specific solc compiler version matching our pragma ^0.8.0
    solc_version = '0.8.20'
    print(f"Ensuring solc version {solc_version} is installed...")
    install_solc(solc_version)

    # 3. Compile the contract using solcx
    print("Compiling ThreatIntel.sol...")
    compiled_sol = compile_source(
        contract_source,
        output_values=['abi', 'bin'],
        solc_version=solc_version
    )

    # The result is a dictionary. E.g. {'<stdin>:ThreatIntel': {...}}
    contract_id, contract_interface = compiled_sol.popitem()
    abi = contract_interface['abi']
    bytecode = contract_interface['bin']

    # 4. Deploy the contract
    print("Deploying contract to the local Geth network...")
    ThreatIntel = w3.eth.contract(abi=abi, bytecode=bytecode)
    
    # Build transaction
    nonce = w3.eth.get_transaction_count(deployer_address)
    transaction = ThreatIntel.constructor().build_transaction({
        'chainId': chain_id,
        'from': deployer_address,
        'nonce': nonce,
        'gasPrice': w3.eth.gas_price,
        'gas': 2000000 # Explicit gas limit for reliable deployment in Geth PoA
    })

    if private_key:
        signed_tx = w3.eth.account.sign_transaction(transaction, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    else:
        # Fallback to node-unlocked account
        tx_hash = w3.eth.send_transaction(transaction)

    # Wait for the transaction to be mined
    print(f"Deployment transaction sent: {tx_hash.hex()}. Waiting for receipt...")
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    contract_address = tx_receipt.contractAddress
    print(f"Contract deployed successfully at address: {contract_address}")

    # 5. Output the deployed Contract Address and ABI to a local JSON file
    contract_data = {
        'address': contract_address,
        'abi': abi
    }
    
    with open(output_file, 'w') as f:
        json.dump(contract_data, f, indent=4)
        
    print(f"Contract address and ABI saved to: {output_file}")

if __name__ == "__main__":
    deploy_contract()
