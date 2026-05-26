"""
Trust Plane component: Utilities for Ryu controller to interface with the Geth blockchain.
"""
import json
import os
import logging
import threading
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()
from ryu.lib import hub


def _normalise_private_key(private_key):
    if not private_key:
        return None
    return private_key if private_key.startswith('0x') else f'0x{private_key}'


def _inject_poa_middleware(w3):
    """
    Support both Web3.py v5 and v6/v7 naming for the Geth PoA middleware.
    """
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except ImportError:
        try:
            from web3.middleware import geth_poa_middleware
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except ImportError:
            return


def _read_chain_id(w3):
    try:
        return int(w3.eth.chain_id)
    except Exception:
        return None


def _fill_signed_transaction_defaults(w3, tx, default_gas):
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


class DLTManager:
    """
    Manages the Web3 connection and smart contract interactions.
    Ensures non-blocking behavior for the Ryu eventlet loop.
    """
    def __init__(self):
        # Setup logger for the DLT Manager
        self.logger = logging.getLogger('DLTManager')
        self.logger.setLevel(logging.INFO)
        self.enabled = False
        self.w3 = None
        self.account = None
        self.private_key = None
        self.chain_id = None
        self.contract = None
        self.contract_address = None
        self.abi = None
        self._tx_lock = threading.Lock()

        # In orchestrated mode, NetworkOrchestrator pushes account/contract data
        # through the controller API after startup.
        if os.environ.get('USE_DLT_ORCHESTRATOR', '0') == '1':
            self.logger.info("DLTManager waiting for orchestrator configuration.")
            return

        self._init_from_contract_data()

    def _init_from_contract_data(self):
        """
        Initialize from blockchain/contract_data.json for local dev mode.
        This path supports Geth --dev or any node with an unlocked account.
        """
        rpc_url = os.environ.get('DLT_RPC_URL', 'http://127.0.0.1:8545')
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        _inject_poa_middleware(self.w3)
        if not self.w3.is_connected():
            self.logger.error("Failed to connect to the Ethereum node at %s", rpc_url)
            return

        self.logger.info("Successfully connected to Ethereum node.")

        if len(self.w3.eth.accounts) > 0:
            self.account = self.w3.eth.accounts[0]
            self.w3.eth.default_account = self.account
        else:
            self.logger.error("No accounts found on the Ethereum node.")
            return

        base_dir = os.path.dirname(os.path.abspath(__file__))
        contract_data_path = os.path.join(base_dir, '..', 'blockchain', 'contract_data.json')

        try:
            with open(contract_data_path, 'r') as f:
                contract_data = json.load(f)

            env_contract = os.environ.get('CONTRACT_ADDRESS', '')
            self.contract_address = env_contract if env_contract else contract_data['address']
            self.abi = contract_data['abi']
            self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.abi)
            self.enabled = True
            self.logger.info("Loaded ThreatIntel contract at %s", self.contract_address)

        except FileNotFoundError:
            self.logger.error("Contract data file not found at %s. Ensure deploy.py has been run.", contract_data_path)
        except Exception as e:
            self.logger.error("Error loading contract data: %s", e)

    def init_stats(self, info):
        """
        Initialize from data pushed by NetworkOrchestrator. The repo stores no
        private keys; the orchestrator creates or receives them at runtime.
        """
        try:
            rpc_url = info['eth_node']
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            _inject_poa_middleware(self.w3)
            if not self.w3.is_connected():
                self.logger.error("Failed to connect to orchestrated Ethereum node at %s", rpc_url)
                return

            self.account = Web3.to_checksum_address(info['address'])
            self.private_key = _normalise_private_key(info.get('private_key'))
            self.chain_id = int(info.get('chain_id')) if info.get('chain_id') else _read_chain_id(self.w3)
            self.contract_address = Web3.to_checksum_address(info['contract_address'])
            self.abi = info['abi']
            self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.abi)
            self.enabled = True
            self.logger.info("Loaded orchestrated ThreatIntel contract at %s for %s",
                             self.contract_address, self.account)
        except Exception as e:
            self.logger.error("Error initializing DLT Manager from orchestrator data: %s", e)

    def publish_threat(self, ip_address):
        """
        Submits a transaction to call reportThreat on the smart contract.
        Wraps the web3 transaction in a green thread to be non-blocking.
        """
        if not self.enabled:
            self.logger.error("DLT is not ready. Skipping publish_threat for %s", ip_address)
            return
        hub.spawn(self._publish_threat_task, ip_address)

    def _publish_threat_task(self, ip_address):
        """
        Internal task to execute the transaction without blocking the main event loop.
        """
        try:
            self.logger.info("Publishing threat for IP: %s", ip_address)
            tx_hash = self._send_transaction(self.contract.functions.reportThreat(ip_address))
            self.logger.info("Threat published. Tx Hash: %s", tx_hash.hex())
        except Exception as e:
            self.logger.error("Failed to publish threat for %s: %s", ip_address, e)

    def update_threat_status(self, ip_address, status_int):
        """
        Submits a transaction to call updateStatus on the smart contract.
        Wraps the web3 transaction in a green thread to be non-blocking.
        """
        if not self.enabled:
            self.logger.error("DLT is not ready. Skipping update_threat_status for %s", ip_address)
            return
        hub.spawn(self._update_threat_status_task, ip_address, status_int)

    def _update_threat_status_task(self, ip_address, status_int):
        """
        Internal task to execute the status update transaction.
        """
        try:
            self.logger.info("Updating threat status for IP: %s to %s", ip_address, status_int)
            tx_hash = self._send_transaction(self.contract.functions.updateStatus(ip_address, status_int))
            self.logger.info("Status updated. Tx Hash: %s", tx_hash.hex())
        except Exception as e:
            self.logger.error("Failed to update status for %s: %s", ip_address, e)

    def get_threat_status(self, ip_address):
        """
        Read the current DLT status for an IoC. Returns None when the DLT is
        unavailable or the contract call fails.
        """
        if not self.enabled:
            self.logger.error("DLT is not ready. Skipping get_threat_status for %s", ip_address)
            return None

        try:
            return self.contract.functions.getThreatStatus(ip_address).call()
        except Exception:
            try:
                return self.contract.functions.threats(ip_address).call()[2]
            except Exception as e:
                self.logger.error("Failed to read threat status for %s: %s", ip_address, e)
                return None

    def _send_transaction(self, contract_function):
        """
        Send a contract transaction through either a node-unlocked account or a
        runtime-provided private key. The private key path is used by the secure
        orchestrated DLT flow.
        """
        if not self.private_key:
            return contract_function.transact({'from': self.account})

        with self._tx_lock:
            tx = {
                'from': self.account,
                'nonce': self.w3.eth.get_transaction_count(self.account, 'pending'),
            }
            if self.chain_id is not None:
                tx['chainId'] = self.chain_id

            built_tx = contract_function.build_transaction(tx)
            built_tx = _fill_signed_transaction_defaults(self.w3, built_tx, default_gas=500_000)
            signed_tx = self.w3.eth.account.sign_transaction(built_tx, private_key=self.private_key)
            raw_tx = getattr(signed_tx, 'raw_transaction', None)
            if raw_tx is None:
                raw_tx = signed_tx.rawTransaction
            return self.w3.eth.send_raw_transaction(raw_tx)

    def start_event_listener(self, callback_func):
        """
        Asynchronously listens for ThreatReported and StatusUpdated events.
        Passes the event data to callback_func.
        """
        hub.spawn(self._event_listener_loop, callback_func)

    @staticmethod
    def _create_event_filter(event_cls):
        try:
            return event_cls.create_filter(from_block='latest')
        except TypeError:
            return event_cls.create_filter(fromBlock='latest')

    def _event_listener_loop(self, callback_func):
        """
        Polling loop to fetch new events without blocking Ryu.
        Uses hub.sleep() to yield control back to the Ryu eventlet loop.
        """
        self.logger.info("Starting DLT event listener loop...")
        try:
            threat_filter = None
            status_filter = None

            while True:
                try:
                    if not self.enabled:
                        hub.sleep(2)
                        continue

                    if threat_filter is None:
                        threat_filter = self._create_event_filter(self.contract.events.ThreatReported)
                    if status_filter is None:
                        status_filter = self._create_event_filter(self.contract.events.StatusUpdated)

                    for event in threat_filter.get_new_entries():
                        self.logger.info("Caught ThreatReported event")
                        callback_func(event)

                    for event in status_filter.get_new_entries():
                        self.logger.info("Caught StatusUpdated event")
                        callback_func(event)

                except Exception as e:
                    self.logger.error("Error while polling events: %s", e)
                    threat_filter = None
                    status_filter = None

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

    def init_stats(self, info):
        self.logger.info("MOCK: Ignoring orchestrator DLT info.")

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
        self._append_event('ThreatReported', {'ipAddress': ip_address})

    def update_threat_status(self, ip_address, status_int):
        self.logger.info("MOCK: Updating threat status for IP: %s to %s", ip_address, status_int)
        hub.spawn(self._mock_update_delay, ip_address, status_int)

    def get_threat_status(self, ip_address):
        self.logger.info("MOCK: Reading threat status for IP: %s", ip_address)
        return None

    def _mock_update_delay(self, ip_address, status_int):
        hub.sleep(10)
        self.logger.info("MOCK: Status updated. Tx Hash: 0xmockhash456")
        self._append_event('StatusUpdated', {'ipAddress': ip_address, 'status': status_int})

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
