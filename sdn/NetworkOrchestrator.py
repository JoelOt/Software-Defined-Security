#!/usr/bin/env python3
"""
Runtime DLT orchestrator.

This is a cleaned-up version of the DLT branch idea: it deploys ThreatIntel,
creates per-controller Ethereum accounts, funds them, and pushes the runtime
DLT details to each Ryu controller API. Secrets are supplied via environment or
created at runtime; they are not stored in the repository.
"""
import argparse
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv
from web3 import Web3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from blockchain.deploy import compile_contract, inject_poa_middleware, wait_for_connection


load_dotenv()


def _normalise_private_key(private_key):
    if not private_key:
        return None
    return private_key if private_key.startswith('0x') else f'0x{private_key}'


def _split_csv(value):
    return [item.strip() for item in value.split(',') if item.strip()]


class NetworkOrchestrator:
    def __init__(self, rpc_url, sdn_ports, agent_names, chain_id=None, deployer_private_key=None):
        self.rpc_url = rpc_url
        self.sdn_ports = sdn_ports
        self.agent_names = agent_names
        self.chain_id = chain_id
        self.deployer_private_key = _normalise_private_key(deployer_private_key)
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        inject_poa_middleware(self.w3)
        if not wait_for_connection(self.w3, rpc_url):
            raise RuntimeError(f"Could not connect to Ethereum node at {rpc_url}")

        if self.deployer_private_key:
            self.deployer_account = self.w3.eth.account.from_key(self.deployer_private_key)
            self.deployer_address = self.deployer_account.address
            if self.chain_id is None:
                self.chain_id = self._read_chain_id()
        elif self.w3.eth.accounts:
            self.deployer_account = None
            self.deployer_address = self.w3.eth.accounts[0]
        else:
            raise RuntimeError("No deployer account available. Set DLT_ORCHESTRATOR_PRIVATE_KEY.")

    @classmethod
    def from_env(cls):
        config = cls._load_optional_config(os.environ.get('DLT_ORCHESTRATOR_CONFIG'))
        rpc_url = (
            os.environ.get('DLT_ORCHESTRATOR_RPC_URL')
            or os.environ.get('DLT_RPC_URL')
            or config.get('dlt_rpc_url')
            or 'http://127.0.0.1:8545'
        )
        sdn_ports_value = os.environ.get('SDN_API_PORTS')
        if sdn_ports_value:
            sdn_ports = [int(port) for port in _split_csv(sdn_ports_value)]
        else:
            sdn_ports = [int(port) for port in config.get('sdn_api_ports', [5000, 5001])]

        agent_names_value = os.environ.get('DLT_AGENT_NAMES')
        if agent_names_value:
            agent_names = _split_csv(agent_names_value)
        else:
            agent_names = config.get('agent_names', ['DomainA', 'DomainB'])

        chain_id = os.environ.get('CHAIN_ID') or config.get('chain_id')
        private_key = os.environ.get('DLT_ORCHESTRATOR_PRIVATE_KEY') or os.environ.get('PRIVATE_KEY')
        if len(sdn_ports) != len(agent_names):
            raise RuntimeError("SDN_API_PORTS and DLT_AGENT_NAMES must have the same number of entries.")
        return cls(
            rpc_url=rpc_url,
            sdn_ports=sdn_ports,
            agent_names=agent_names,
            chain_id=int(chain_id) if chain_id else None,
            deployer_private_key=private_key,
        )

    @staticmethod
    def _load_optional_config(path):
        if not path:
            path = os.path.join('blockchain', 'orchestrator_config.json')
        if not os.path.exists(path):
            return {}
        with open(path, 'r') as f:
            return json.load(f)

    def _read_chain_id(self):
        try:
            return int(self.w3.eth.chain_id)
        except Exception:
            return None

    def deploy_contract(self):
        contract_path = os.environ.get('THREAT_CONTRACT_PATH', os.path.join('blockchain', 'ThreatIntel.sol'))
        with open(contract_path, 'r') as f:
            contract_source = f.read()

        abi, bytecode = compile_contract(contract_source)
        contract_factory = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash = self._send_transaction(contract_factory.constructor())
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        self.contract_address = receipt.contractAddress
        self.abi = abi
        print(f"ThreatIntel deployed at {self.contract_address}")

    def create_controller_accounts(self, funding_ether=0.05):
        accounts = []
        for name in self.agent_names:
            account = self.w3.eth.account.create()
            self._fund_account(account.address, funding_ether)
            accounts.append({
                'name': name,
                'address': account.address,
                'private_key': account.key.hex(),
                'eth_node': self.rpc_url,
                'contract_address': self.contract_address,
                'abi': self.abi,
                'chain_id': self.chain_id,
            })
        return accounts

    def _fund_account(self, address, funding_ether):
        tx = {
            'from': self.deployer_address,
            'to': address,
            'value': Web3.to_wei(funding_ether, 'ether'),
        }
        tx_hash = self._send_transaction_dict(tx)
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

    def _send_transaction(self, transaction_builder):
        tx = {
            'from': self.deployer_address,
            'nonce': self.w3.eth.get_transaction_count(self.deployer_address, 'pending'),
        }
        if self.chain_id is not None:
            tx['chainId'] = self.chain_id
        built_tx = transaction_builder.build_transaction(tx)
        if self.deployer_private_key:
            built_tx = self._fill_signed_transaction_defaults(built_tx, default_gas=5_000_000)
        return self._send_built_transaction(built_tx)

    def _send_transaction_dict(self, tx):
        tx = dict(tx)
        if self.deployer_private_key:
            tx = self._fill_signed_transaction_defaults(tx, default_gas=21_000)
        return self._send_built_transaction(tx)

    def _fill_signed_transaction_defaults(self, tx, default_gas):
        tx = dict(tx)
        tx.setdefault('nonce', self.w3.eth.get_transaction_count(self.deployer_address, 'pending'))
        if self.chain_id is not None:
            tx.setdefault('chainId', self.chain_id)

        def buffered_gas(gas):
            return int(gas * 1.2) + 10_000

        if 'gas' not in tx:
            try:
                tx['gas'] = buffered_gas(self.w3.eth.estimate_gas(tx))
            except Exception:
                tx['gas'] = default_gas
        else:
            tx['gas'] = buffered_gas(int(tx['gas']))

        if (
            'gasPrice' not in tx
            and 'maxFeePerGas' not in tx
            and 'maxPriorityFeePerGas' not in tx
        ):
            tx['gasPrice'] = self.w3.eth.gas_price

        return tx

    def _send_built_transaction(self, built_tx):
        if not self.deployer_private_key:
            return self.w3.eth.send_transaction(built_tx)
        signed_tx = self.w3.eth.account.sign_transaction(built_tx, private_key=self.deployer_private_key)
        raw_tx = getattr(signed_tx, 'raw_transaction', None)
        if raw_tx is None:
            raw_tx = signed_tx.rawTransaction
        return self.w3.eth.send_raw_transaction(raw_tx)

    def push_controller_config(self, accounts):
        for port, account in zip(self.sdn_ports, accounts):
            url = f"http://127.0.0.1:{port}/DLT_info"
            self._post_with_retry(url, account)

    @staticmethod
    def _post_with_retry(url, payload, attempts=10, delay=2):
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(url, json=payload, timeout=5)
                if response.status_code == 200:
                    print(f"Configured controller at {url}")
                    return
                print(f"Controller at {url} returned {response.status_code}: {response.text}")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                print(f"Waiting for controller API at {url} ({attempt}/{attempts})")
            time.sleep(delay)
        raise RuntimeError(f"Could not configure controller at {url}")

    def run(self):
        self.deploy_contract()
        accounts = self.create_controller_accounts()
        self.push_controller_config(accounts)
        print("DLT orchestration complete.")


def parse_args():
    parser = argparse.ArgumentParser(description="Deploy ThreatIntel and configure SDN controllers.")
    parser.add_argument('--once', action='store_true', help='Run once and exit after pushing controller config.')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    orchestrator = NetworkOrchestrator.from_env()
    orchestrator.run()
    if not args.once:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Orchestrator terminated.")
