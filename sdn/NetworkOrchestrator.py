import json
import os
import random
import requests
import solcx
import time as t
from web3 import Web3
from web3.middleware import geth_poa_middleware
from solcx import compile_standard


class NetworkOrchestrator(object):
    def __init__(self, sdn_ports):

        self.sdn_ports = sdn_ports
        credentials_path = os.path.join('blockchain', 'dlt-network-docker', 'code', 'credentials.json')
        with open(credentials_path, 'r') as json_file:
            info = json.load(json_file)
        self.eth_nodes = info["eth_nodes"]
        self.eth_address = info["eth_address"]
        self.private_key = info["private_key"]
        self.chain_id = info["chain_id"]
        self.agent_names = info["agent_names"]
        self.contract_name = ""
        self.accounts = []
        self.contract_address = None
        self.contract_abi = None
        self.contract = None
        self.contract_deployed = False
        self.agents_registered = None
        self.key_set = False
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.eth_nodes[1]))
        except:
            raise Exception("Web3 connection failed")
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        try:
            self.nonce = self.web3.eth.get_transaction_count(self.eth_address)
        except:
            raise Exception("DLT connection failed")

    def deploy_contract(self, contract_path):
        # Function to deploy the contract to the DLT.
        with open(contract_path, "r") as file:
            contact_list_file = file.read()

        compiled_sol = compile_standard(
            {
                "language": "Solidity",
                "sources": {contract_path: {"content": contact_list_file}},
                "settings": {
                    "outputSelection": {
                        "*": {
                            "*": ["abi", "metadata", "evm.bytecode", "evm.bytecode.sourceMap"]
                        }
                    }
                },
            },
            solc_version="0.8.12",
        )
        self.contract_name = os.path.basename(contract_path).split(".")[0]
        bytecode = compiled_sol["contracts"][contract_path][self.contract_name]["evm"]["bytecode"]["object"]
        self.contract_abi = \
            json.loads(compiled_sol["contracts"][contract_path][self.contract_name]["metadata"])["output"]["abi"]
        Contract = self.web3.eth.contract(abi=self.contract_abi, bytecode=bytecode)
        self.nonce = self.web3.eth.get_transaction_count(self.eth_address)
        transaction = Contract.constructor().build_transaction(
            {"chainId": self.chain_id, "gasPrice": self.web3.eth.gas_price, "from": self.eth_address,
             "nonce": self.nonce}
        )
        sign_transaction = self.web3.eth.account.sign_transaction(transaction, private_key=self.private_key)
        transaction_hash = self.web3.eth.send_raw_transaction(sign_transaction.rawTransaction)
        transaction_receipt = self.web3.eth.wait_for_transaction_receipt(transaction_hash)
        self.contract_address = transaction_receipt.contractAddress
        self.contract = self.web3.eth.contract(abi=self.contract_abi, address=self.contract_address)

    def import_and_unlock_accounts(self, accounts, names):
        # Function to import and unlock accounts using their private keys
        for i in range(len(accounts)):
            private_key = accounts[names[i]]['private_key']
            decrypted_account = self.web3.eth.account.from_key(private_key)
            try:
                self.web3.geth.personal.import_raw_key(private_key, "")
                self.web3.geth.personal.unlock_account(decrypted_account.address, "")
                print(f"Successfully unlocked account {decrypted_account.address}")
            except Exception as e:
                print(f"An error occurred while unlocking account {decrypted_account.address}: {e}")

    def create_account_and_fund(self, names, value_ether=0.05):
        # Function to create the clients accounts and give them al the necesary information
        accounts = {}
        print(len(names))
        for i in range(len(names)):
            account = self.web3.eth.account.create()
            accounts[str(names[i])] = {
                'name': names[i],
                'address': account.address,
                'private_key': account._private_key.hex()[2:],  # Remove the "0x" prefix from the private key
                'balance': self.web3.eth.get_balance(account.address)
            }

        # Import and unlock the accounts
        self.import_and_unlock_accounts(accounts, names)

        # Now, let's fund the new accounts from the pre-funded address
        from_address = self.web3.eth.accounts[0]  # Assuming the pre-funded address is the first account
        value_wei = Web3.to_wei(value_ether, "ether")
        
        for i in range(len(names)):
            to_address = accounts[names[i]]['address']
            self.web3.eth.send_transaction({
                'from': from_address,
                'to': to_address,
                'value': value_wei
            })

        # Add a delay to allow time for transactions to be processed
        t.sleep(3)

        # Now, let's fetch and update the balances after the transfers
        for i in range(len(names)):
            accounts[names[i]]['balance'] = self.web3.eth.get_balance(accounts[names[i]]['address'])
            accounts[names[i]]['eth_node'] = random.choice(self.eth_nodes)
            accounts[names[i]]['contract_address'] = self.contract_address
            accounts[names[i]]['eth_address'] = self.eth_address

        return accounts

    def request_dlt_addresses(self, agent_names):
        # Function that returns the created accounts based on the agent names
        accounts = self.create_account_and_fund(agent_names)
        return accounts

    def send_signed_transaction(self, build_transaction):
        # Function to send a transaction but signed with a secret key

        # Sign the transaction
        try:
            signed_txn = self.web3.eth.account.sign_transaction(build_transaction, self.private_key)
        except:
            raise Exception("Couldn't signt the transaction" + str(build_transaction))
        # Send the signed transaction
        try:
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        except:
            raise Exception("Error sendind the transaction")
        # Increment the nonce
        self.nonce += 1

        return tx_hash

    def register_agents(self, accounts, names):
        # Function to add the accounts information to the Smart Contract so that they can actually use it

        agent_addresses = []
        agent_names = []
        self.nonce = self.web3.eth.get_transaction_count(self.eth_address)
        for i in range(len(accounts)):
            agent_addresses.append(accounts[names[i]]["address"])
            agent_names.append(names[i])
        tx_data = self.contract.functions.registerAgents(
            agent_addresses,
            agent_names
        ).build_transaction({'from': self.eth_address, 'nonce': self.nonce})

        # Send the signed transaction
        self.send_signed_transaction(tx_data)

    def automatic_start(self):
        # Function that does all the basics to be able to connect clients and DLT
        self.contract_name = os.path.join('blockchain', 'dlt-network-docker', 'code', 'ThreatIntel.sol')
        self.deploy_contract(self.contract_name)
        self.accounts = self.request_dlt_addresses(self.agent_names)
        print(self.accounts)
        # self.register_agents(self.accounts, self.agent_names) # ThreatIntel.sol doesn't have registration
        for i in range(len(self.accounts)):
            self.accounts[self.agent_names[i]]["contract_name"] = self.contract_name

        for i in range(len(self.accounts)):
            data_to_send = self.accounts[self.agent_names[i]]
            port = self.sdn_ports[i]
            url = f"http://127.0.0.1:{port}/DLT_info"
            
            # Implementation of a retry mechanism to allow SDN Controllers time to initialize their API servers.
            max_retries = 10
            success = False
            for attempt in range(max_retries):
                try:
                    # Attempt to push DLT credentials to the SDN Controller
                    response = requests.post(url, json=data_to_send, timeout=5)
                    if response.status_code == 200:
                        print(f"Successfully pushed DLT info to SDN Controller at port {port}")
                        success = True
                        break
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    print(f"Waiting for SDN Controller on port {port}... (Attempt {attempt+1}/{max_retries})")
                    t.sleep(2)
            
            if not success:
                raise Exception(f"Could not connect to SDN API at port {port} after {max_retries} attempts. "
                                "Ensure Ryu controllers are running and ports match ports_info.json.")

    def run(self):
        print("Connecting with DLT...")
        self.automatic_start()
        print("SDN Controllers configured")
        try:
            while True:
                t.sleep(1)
        except KeyboardInterrupt:
            print("Orchestrator terminated.")

if __name__ == "__main__":
    solcx.install_solc('0.8.12')
    ports_info_path = os.path.join('blockchain', 'dlt-network-docker', 'code', 'ports_info.json')
    with open(ports_info_path, 'r') as json_file:
        info = json.load(json_file)

    SDN_ports = info["SDN_ports"]
    no = NetworkOrchestrator(SDN_ports)
    no.run()
