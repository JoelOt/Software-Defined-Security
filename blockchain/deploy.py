"""
Trust Plane component: Smart Contract deployment script for the federated SDN architecture.
"""
import json
import os
from web3 import Web3
from solcx import compile_source, install_solc
from dotenv import load_dotenv

load_dotenv()

def deploy_contract():
    # 1. Connect to local Geth RPC
    rpc_url = os.environ.get('DLT_RPC_URL', 'http://127.0.0.1:8545')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print(f"Error: Failed to connect to the Ethereum node at {rpc_url}")
        return

    print("Successfully connected to Ethereum node.")
    
    # 2. Use the first account in w3.eth.accounts
    if len(w3.eth.accounts) == 0:
        print("Error: No accounts found on the Ethereum node.")
        return
        
    deployer_account = w3.eth.accounts[0]
    print(f"Using deployer account: {deployer_account}")

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
    
    # Transact with the first account (assumes it's unlocked by the Geth node configuration)
    tx_hash = ThreatIntel.constructor().transact({'from': deployer_account})

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
