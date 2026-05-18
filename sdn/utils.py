"""
Trust Plane component: Utilities for Ryu controller to interface with the Geth blockchain.
"""
import json
import os
import logging
from web3 import Web3
from web3.middleware import geth_poa_middleware
from solcx import compile_standard
from dotenv import load_dotenv

load_dotenv()
from ryu.lib import hub

class DLTManager:
    """
    Manages the Web3 connection and smart contract interactions.
    Ensures non-blocking behavior for the Ryu eventlet loop.
    """
    def __init__(self):
        # Setup logger for the DLT Manager
        self.logger = logging.getLogger('DLTManager')
        self.logger.setLevel(logging.INFO)
        self.configured = False
        self.w3 = None
        self.contract = None
        self.account = None
        self.private_key = None

    def init_stats(self, info):
        """
        Initializes the manager with data provided by the NetworkOrchestrator via the API.
        """
        try:
            self.account = info['address']
            self.private_key = info['private_key']
            self.w3 = Web3(Web3.HTTPProvider(info['eth_node']))
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            
            contract_name = info["contract_name"]
            # Ensure we point to the blockchain folder where the .sol resides
            contract_path = os.path.join('blockchain', 'dlt-network-docker', 'code', contract_name + ".sol")
            
            with open(contract_path, "r") as file:
                source = file.read()
            
            compiled_sol = compile_standard(
                {
                    "language": "Solidity",
                    "sources": {contract_path: {"content": source}},
                    "settings": {"outputSelection": {"*": {"*": ["abi", "metadata"]}}},
                },
                solc_version="0.8.12",
            )
            
            abi = json.loads(compiled_sol["contracts"][contract_path][contract_name]["metadata"])["output"]["abi"]
            self.contract_address = Web3.to_checksum_address(info['contract_address'])
            self.contract = self.w3.eth.contract(abi=abi, address=self.contract_address)
            
            self.logger.info("Successfully connected to node and loaded contract %s", contract_name)
            self.configured = True

        except Exception as e:
            self.logger.error("Error initializing DLT Manager: %s", e)

    def publish_threat(self, ip_address):
        """
        Submits a transaction to call reportThreat on the smart contract.
        Wraps the web3 transaction in a green thread to be non-blocking.
        """
        hub.spawn(self._publish_threat_task, ip_address)

    def _publish_threat_task(self, ip_address):
        """
        Internal task to execute the transaction without blocking the main event loop.
        """
        try:
            if not self.configured:
                return
            self.logger.info("Publishing threat for IP: %s", ip_address)
            
            nonce = self.w3.eth.get_transaction_count(self.account)
            tx = self.contract.functions.reportThreat(ip_address).build_transaction({
                'from': self.account,
                'nonce': nonce,
                'gasPrice': self.w3.eth.gas_price
            })
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            self.logger.info("Threat published. Tx Hash: %s", tx_hash.hex())
        except Exception as e:
            self.logger.error("Failed to publish threat for %s: %s", ip_address, e)

    def update_threat_status(self, ip_address, status_int):
        """
        Submits a transaction to call updateStatus on the smart contract.
        Wraps the web3 transaction in a green thread to be non-blocking.
        """
        hub.spawn(self._update_threat_status_task, ip_address, status_int)

    def _update_threat_status_task(self, ip_address, status_int):
        """
        Internal task to execute the status update transaction.
        """
        try:
            if not self.configured:
                return
            self.logger.info("Updating threat status for IP: %s to %s", ip_address, status_int)
            
            nonce = self.w3.eth.get_transaction_count(self.account)
            tx = self.contract.functions.updateStatus(ip_address, status_int).build_transaction({
                'from': self.account,
                'nonce': nonce,
                'gasPrice': self.w3.eth.gas_price
            })
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            self.logger.info("Status updated. Tx Hash: %s", tx_hash.hex())
        except Exception as e:
            self.logger.error("Failed to update status for %s: %s", ip_address, e)

    def start_event_listener(self, callback_func):
        """
        Asynchronously listens for ThreatReported and StatusUpdated events.
        Passes the event data to callback_func.
        """
        hub.spawn(self._event_listener_loop, callback_func)

    def _event_listener_loop(self, callback_func):
        """
        Polling loop to fetch new events without blocking Ryu.
        Uses hub.sleep() to yield control back to the Ryu eventlet loop.
        """
        self.logger.info("Starting DLT event listener loop...")
        try:
            # Wait for the orchestrator to provide contract info
            while not self.configured:
                hub.sleep(1)
                
            # Create event filters looking from the latest block
            threat_filter = self.contract.events.ThreatReported.create_filter(fromBlock='latest')
            status_filter = self.contract.events.StatusUpdated.create_filter(fromBlock='latest')
            
            while True:
                try:
                    # Poll for new ThreatReported events
                    for event in threat_filter.get_new_entries():
                        self.logger.info("Caught ThreatReported event")
                        callback_func(event)
                        
                    # Poll for new StatusUpdated events
                    for event in status_filter.get_new_entries():
                        self.logger.info("Caught StatusUpdated event")
                        callback_func(event)
                        
                except Exception as e:
                    self.logger.error("Error while polling events: %s", e)
                
                # Crucial: Yield to Ryu's eventlet loop
                hub.sleep(2)
                
        except Exception as e:
            self.logger.error("Failed to initialize event filters: %s", e)
