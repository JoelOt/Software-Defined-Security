"""
Trust Plane component: Utilities for Ryu controller to interface with the Geth blockchain.
"""
import json
import os
import logging
from enum import IntEnum
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()
from ryu.lib import hub

class ThreatStatus(IntEnum):
    NONE = 0
    PENDING = 1
    QUARANTINED = 2

class DLTManager:
    """
    Manages the Web3 connection and smart contract interactions.
    Ensures non-blocking behavior for the Ryu eventlet loop.
    """
    def __init__(self):
        # Setup logger for the DLT Manager
        self.logger = logging.getLogger('DLTManager')
        self.logger.setLevel(logging.INFO)
        
        # 1. Connect to local Geth RPC
        rpc_url = os.environ.get('DLT_RPC_URL', 'http://127.0.0.1:8545')
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            self.logger.error("Failed to connect to the Ethereum node at %s", rpc_url)
            return

        # Inject Geth PoA middleware to validate Clique consensus blocks (longer extraData)
        try:
            from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
        except ImportError:
            from web3.middleware import geth_poa_middleware as poa_middleware
        self.w3.middleware_onion.inject(poa_middleware, layer=0)
            
        self.logger.info("Successfully connected to Ethereum node.")
        
        # Setup default account
        if len(self.w3.eth.accounts) > 0:
            self.account = self.w3.eth.accounts[0]
            self.w3.eth.default_account = self.account
        else:
            self.logger.error("No accounts found on the Ethereum node.")
            return

        # 2. Load ABI and Contract Address
        base_dir = os.path.dirname(os.path.abspath(__file__))
        contract_data_path = os.path.join(base_dir, '..', 'blockchain', 'contract_data.json')
        
        try:
            with open(contract_data_path, 'r') as f:
                contract_data = json.load(f)
                
            env_contract = os.environ.get('CONTRACT_ADDRESS', '')
            self.contract_address = env_contract if env_contract else contract_data['address']
            self.abi = contract_data['abi']
            
            # Initialize the contract instance
            self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.abi)
            self.logger.info("Loaded ThreatIntel contract at %s", self.contract_address)
            
        except FileNotFoundError:
            self.logger.error("Contract data file not found at %s. Ensure deploy.py has been run.", contract_data_path)
        except Exception as e:
            self.logger.error("Error loading contract data: %s", e)

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
            self.logger.info("Publishing threat for IP: %s", ip_address)
            # Send transaction using the default account
            tx_hash = self.contract.functions.reportThreat(ip_address).transact({'from': self.account})
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
            try:
                status_label = ThreatStatus(status_int).name
            except ValueError:
                status_label = str(status_int)
            self.logger.info("Updating threat status for IP: %s to %s", ip_address, status_label)
            tx_hash = self.contract.functions.updateStatus(ip_address, status_int).transact({'from': self.account})
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
            # Create event filters looking from the latest block (handles web3.py v5 and v6+ signatures)
            try:
                threat_filter = self.contract.events.ThreatReported.create_filter(from_block='latest')
                status_filter = self.contract.events.StatusUpdated.create_filter(from_block='latest')
            except TypeError:
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


class TestDLTManager:
    """
    Mock DLT Manager for testing without a real Geth network.
    Implements the same interface as DLTManager but only logs actions.
    It can also simulate DLT events triggering back to the controller
    by using a shared file for inter-process communication.
    """
    def __init__(self):
        self.logger = logging.getLogger('TestDLTManager')
        self.logger.setLevel(logging.INFO)
        self.logger.info("Initialized TestDLTManager (Mock Mode with IPC).")
        self.callback = None
        self.shared_file = '/tmp/mock_dlt_events.jsonl'
        self.last_pos = 0
        
        # Ensure file exists
        if not os.path.exists(self.shared_file):
            with open(self.shared_file, 'w') as f:
                pass

    def _append_event(self, event_name, args):
        event_data = {
            'event': event_name,
            'args': args
        }
        with open(self.shared_file, 'a') as f:
            f.write(json.dumps(event_data) + '\n')

    def publish_threat(self, ip_address):
        self.logger.info("MOCK: Publishing threat for IP: %s", ip_address)
        # Simulate network delay then fire event
        hub.spawn(self._mock_publish_delay, ip_address)

    def _mock_publish_delay(self, ip_address):
        hub.sleep(1)
        self.logger.info("MOCK: Threat published. Tx Hash: 0xmockhash123")
        self._append_event('ThreatReported', {'ip': ip_address, 'ipAddress': ip_address})

    def update_threat_status(self, ip_address, status_int):
        self.logger.info("MOCK: Updating threat status for IP: %s to %s", ip_address, status_int)
        hub.spawn(self._mock_update_delay, ip_address, status_int)

    def _mock_update_delay(self, ip_address, status_int):
        hub.sleep(10)
        self.logger.info("MOCK: Status updated. Tx Hash: 0xmockhash456")
        self._append_event('StatusUpdated', {
            'ip': ip_address,
            'ipAddress': ip_address,
            'newStatus': status_int,
            'status': status_int
        })

    def start_event_listener(self, callback_func):
        self.logger.info("MOCK: Starting DLT event listener loop...")
        self.callback = callback_func
        # Start reading from current EOF to ignore old mock events
        if os.path.exists(self.shared_file):
            self.last_pos = os.path.getsize(self.shared_file)
        hub.spawn(self._poll_shared_file)
        
    def _poll_shared_file(self):
        class MockEvent:
            def __init__(self, event_name, args):
                self.event = event_name
                self.args = args
                
        while True:
            try:
                if os.path.exists(self.shared_file):
                    with open(self.shared_file, 'r') as f:
                        f.seek(self.last_pos)
                        lines = f.readlines()
                        self.last_pos = f.tell()
                        
                        for line in lines:
                            if line.strip():
                                data = json.loads(line)
                                if self.callback:
                                    self.callback(MockEvent(data['event'], data['args']))
            except Exception as e:
                self.logger.error("MOCK polling error: %s", e)
            
            hub.sleep(2)
