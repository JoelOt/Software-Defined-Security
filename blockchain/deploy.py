"""
Trust Plane component: Smart Contract deployment script for the federated SDN architecture.
"""
import json
import os
import subprocess
import shutil
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

def compile_contract(base_dir, contract_file, solc_version='0.8.31'):
    system_solc = shutil.which("solc")
    if system_solc:
        print(f"System-wide solc detected at: {system_solc}")
        try:
            # Check version info
            version_output = subprocess.run([system_solc, "--version"], capture_output=True, text=True, check=True)
            print(f"System solc version:\n{version_output.stdout.strip()}")
            
            build_dir = os.path.join(base_dir, 'build')
            os.makedirs(build_dir, exist_ok=True)
            
            # Compile using system solc
            subprocess.run([
                system_solc,
                "--abi", "--bin",
                "--evm-version", "paris",
                "-o", build_dir,
                contract_file,
                "--overwrite"
            ], check=True, capture_output=True)
            
            abi_path = os.path.join(build_dir, 'ThreatIntel.abi')
            bin_path = os.path.join(build_dir, 'ThreatIntel.bin')
            
            if os.path.exists(abi_path) and os.path.exists(bin_path):
                print("Successfully compiled contract via system solc!")
                with open(abi_path, 'r') as f:
                    abi = json.load(f)
                with open(bin_path, 'r') as f:
                    bytecode = f.read().strip()
                return abi, bytecode
        except Exception as e:
            print(f"System solc compilation failed or incompatible: {e}. Trying other methods...")

    # 2. Try compiling via Docker (works on AMD64, but has architecture limits on ARM64)
    if shutil.which("docker"):
        print("Docker detected. Attempting to compile ThreatIntel.sol using ethereum/solc container...")
        try:
            uid = os.getuid() if hasattr(os, 'getuid') else 0
            gid = os.getgid() if hasattr(os, 'getgid') else 0
            
            user_flags = []
            if uid and gid:
                user_flags = ["-u", f"{uid}:{gid}"]

            subprocess.run([
                "docker", "run", "--rm"
            ] + user_flags + [
                "-v", f"{base_dir}:/blockchain",
                f"ethereum/solc:{solc_version}",
                "--abi", "--bin",
                "--evm-version", "paris",
                "-o", "/blockchain/build",
                "/blockchain/ThreatIntel.sol",
                "--overwrite"
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            abi_path = os.path.join(base_dir, 'build', 'ThreatIntel.abi')
            bin_path = os.path.join(base_dir, 'build', 'ThreatIntel.bin')
            
            if os.path.exists(abi_path) and os.path.exists(bin_path):
                print("Successfully compiled contract via Docker!")
                with open(abi_path, 'r') as f:
                    abi = json.load(f)
                with open(bin_path, 'r') as f:
                    bytecode = f.read().strip()
                return abi, bytecode
        except subprocess.CalledProcessError as e:
            print(f"Docker compilation failed: {e.stderr.decode('utf-8') if e.stderr else str(e)}. Falling back to solcx...")
        except Exception as e:
            print(f"Docker compilation failed with error: {e}. Falling back to solcx...")

    # 3. Fallback: compile using solcx on the host
    print("Compiling ThreatIntel.sol natively using solcx...")
    from solcx import compile_source, install_solc
    try:
        install_solc(solc_version)
    except Exception as e:
        print(f"Warning: solcx could not ensure solc {solc_version} is installed: {e}")
        
    with open(contract_file, 'r') as f:
        contract_source = f.read()

    compiled_sol = compile_source(
        contract_source,
        output_values=['abi', 'bin'],
        solc_version=solc_version,
        evm_version='paris'
    )
    _, contract_interface = compiled_sol.popitem()
    return contract_interface['abi'], contract_interface['bin']

def deploy_contract():
    # 1. Connect to local Geth RPC
    rpc_url = os.environ.get('DLT_RPC_URL', 'http://127.0.0.1:8545')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print(f"Error: Failed to connect to the Ethereum node at {rpc_url}")
        return

    # Inject Geth PoA middleware to validate Clique consensus blocks (longer extraData)
    try:
        from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
    except ImportError:
        from web3.middleware import geth_poa_middleware as poa_middleware
    w3.middleware_onion.inject(poa_middleware, layer=0)

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

    # 3. Compile the contract using hybrid compilation
    abi, bytecode = compile_contract(base_dir, contract_file)

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
