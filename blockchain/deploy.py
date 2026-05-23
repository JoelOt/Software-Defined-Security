"""
Trust Plane component: Smart Contract deployment script for the federated SDN architecture.
"""
import json
import os
import platform
import shutil
import subprocess
import time
from web3 import Web3
from solcx import compile_source, get_installed_solc_versions, install_solc
from dotenv import load_dotenv

load_dotenv()


def inject_poa_middleware(w3):
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except ImportError:
        try:
            from web3.middleware import geth_poa_middleware
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except ImportError:
            return


def normalise_private_key(private_key):
    if not private_key:
        return None
    return private_key if private_key.startswith('0x') else f'0x{private_key}'


def resolve_chain_id(w3, configured_chain_id):
    if configured_chain_id:
        return int(configured_chain_id)
    try:
        return int(w3.eth.chain_id)
    except Exception:
        return None


def fill_signed_transaction_defaults(w3, tx, default_gas):
    tx = dict(tx)
    def buffered_gas(gas):
        return int(gas * 1.2) + 10_000

    if 'gas' not in tx:
        try:
            tx['gas'] = buffered_gas(w3.eth.estimate_gas(tx))
        except Exception:
            tx['gas'] = default_gas
    else:
        tx['gas'] = buffered_gas(int(tx['gas']))

    if (
        'gasPrice' not in tx
        and 'maxFeePerGas' not in tx
        and 'maxPriorityFeePerGas' not in tx
    ):
        tx['gasPrice'] = w3.eth.gas_price

    return tx


def wait_for_connection(w3, rpc_url, attempts=10, delay=2):
    for attempt in range(1, attempts + 1):
        if w3.is_connected():
            return True
        try:
            _ = w3.client_version
            return True
        except Exception:
            pass
        print(f"Waiting for Ethereum node at {rpc_url} ({attempt}/{attempts})...")
        time.sleep(delay)
    return False


def compile_contract(contract_source):
    solc_version = '0.8.20'
    if platform.machine().lower() in {'aarch64', 'arm64'} and shutil.which('solcjs'):
        return compile_contract_with_solcjs(contract_source)

    try:
        installed_versions = {str(version) for version in get_installed_solc_versions()}
        if solc_version not in installed_versions:
            if shutil.which('solcjs'):
                return compile_contract_with_solcjs(contract_source)
            print(f"Ensuring native solc version {solc_version} is installed...")
            install_solc(solc_version)

        print("Compiling ThreatIntel.sol with native solc...")
        compiled_sol = compile_source(
            contract_source,
            output_values=['abi', 'bin'],
            solc_version=solc_version
        )
        _, contract_interface = compiled_sol.popitem()
        return contract_interface['abi'], contract_interface['bin']
    except Exception as exc:
        print(f"Native solc unavailable ({exc}). Falling back to solcjs.")
        return compile_contract_with_solcjs(contract_source)


def compile_contract_with_solcjs(contract_source):
    solcjs = shutil.which('solcjs')
    if not solcjs:
        raise RuntimeError("solcjs not found. Install it with: npm install -g solc@0.8.20")

    compiler_input = {
        'language': 'Solidity',
        'sources': {
            'ThreatIntel.sol': {
                'content': contract_source,
            },
        },
        'settings': {
            'outputSelection': {
                '*': {
                    '*': ['abi', 'evm.bytecode.object'],
                },
            },
        },
    }

    print("Compiling ThreatIntel.sol with solcjs...")
    result = subprocess.run(
        [solcjs, '--standard-json'],
        input=json.dumps(compiler_input),
        text=True,
        capture_output=True,
        check=True,
    )

    json_start = result.stdout.find('{')
    if json_start == -1:
        raise RuntimeError(f"solcjs did not return JSON output:\n{result.stdout}\n{result.stderr}")
    stdout = result.stdout[json_start:]
    compiler_output = json.loads(stdout)
    errors = [
        err for err in compiler_output.get('errors', [])
        if err.get('severity') == 'error'
    ]
    if errors:
        messages = '\n'.join(err.get('formattedMessage', str(err)) for err in errors)
        raise RuntimeError(f"solcjs compilation failed:\n{messages}")

    contract_interface = compiler_output['contracts']['ThreatIntel.sol']['ThreatIntel']
    abi = contract_interface['abi']
    bytecode = contract_interface['evm']['bytecode']['object']
    return abi, bytecode


def deploy_contract():
    # 1. Connect to local Geth RPC
    rpc_url = os.environ.get('DLT_RPC_URL', 'http://127.0.0.1:8545')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    inject_poa_middleware(w3)
    
    if not wait_for_connection(w3, rpc_url):
        print(f"Error: Failed to connect to the Ethereum node at {rpc_url}")
        return

    print("Successfully connected to Ethereum node.")

    private_key = normalise_private_key(os.environ.get('PRIVATE_KEY'))
    chain_id = None
    if private_key:
        deployer = w3.eth.account.from_key(private_key)
        deployer_account = deployer.address
        chain_id = resolve_chain_id(w3, os.environ.get('CHAIN_ID'))
    else:
        if len(w3.eth.accounts) == 0:
            print("Error: No accounts found on the Ethereum node and PRIVATE_KEY is not set.")
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

    # 3. Compile the contract using native solc or solcjs fallback on ARM64.
    abi, bytecode = compile_contract(contract_source)

    # 4. Deploy the contract
    print("Deploying contract to the local Geth network...")
    ThreatIntel = w3.eth.contract(abi=abi, bytecode=bytecode)

    if private_key:
        tx = {
            'from': deployer_account,
            'nonce': w3.eth.get_transaction_count(deployer_account, 'pending'),
        }
        if chain_id is not None:
            tx['chainId'] = chain_id
        built_tx = ThreatIntel.constructor().build_transaction(tx)
        built_tx = fill_signed_transaction_defaults(w3, built_tx, default_gas=5_000_000)
        signed_tx = w3.eth.account.sign_transaction(built_tx, private_key=private_key)
        raw_tx = getattr(signed_tx, 'raw_transaction', None)
        if raw_tx is None:
            raw_tx = signed_tx.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
    else:
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
