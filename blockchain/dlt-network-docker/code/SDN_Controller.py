import threading
from web3 import Web3
import json
import SDN_api
from solcx import compile_standard

from web3.middleware import geth_poa_middleware

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from keras.models import model_from_json
from sklearn.preprocessing import LabelEncoder


class SDN_Controller(object):
    def __init__(self, portnumber, role):
        self.port_num = int(portnumber)
        self.role = role
        self.nonce = None
        self.private_key = None
        self.eth_address = None
        self.web3_adress = None
        self.web3 = None
        self.contract_abi = None
        self.contract_address = None
        self.contract_name = None
        self.contract_path = None
        self.my_contract = None
        self.eth_address = None
        self.configured = False
        self.sending = False
        self.receiving = False

    def run_model(self, config, weights):
        df = pd.read_csv("dataFile.csv")
        df['target'].value_counts()
        df['Attack Type'].value_counts()

        pmap = {'icmp': 0, 'tcp': 1, 'udp': 2}
        df['protocol_type'] = df['protocol_type'].map(pmap)
        fmap = {'SF': 0, 'S0': 1, 'REJ': 2, 'RSTR': 3, 'RSTO': 4, 'SH': 5, 'S1': 6, 'S2': 7, 'RSTOS0': 8, 'S3': 9,
                'OTH': 10}
        df['flag'] = df['flag'].map(fmap)
        df.drop('service', axis=1, inplace=True)
        df.drop(['target', ], axis=1, inplace=True)
        df = df.dropna(axis=1)
        df = df[[col for col in df if df[col].nunique() > 1]]

        corr = df.select_dtypes(include=['number']).corr()
        cor_thr = 0.98
        corr_matrix = df.select_dtypes(include=['number']).corr().abs()
        upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(np.bool_))
        to_drop = [column for column in upper.columns if any(upper[column] > cor_thr)]
        for i in to_drop:
            df.drop(i, axis=1, inplace=True)

        # Target variable and train set
        Y = df[['Attack Type']]
        X = df.drop(['Attack Type', ], axis=1)
        sc = MinMaxScaler()
        X = sc.fit_transform(X)
        # Split test and train data
        X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.33, random_state=42)

        weights_file = weights

        json_config_raw = open(config).read()
        json_config_raw = json_config_raw.replace('"batch_shape"', '"batch_input_shape"')
        model_dict = json.loads(json_config_raw)
        
        def flatten_dtype(obj):
            if isinstance(obj, dict):
                # If 'dtype' is a nested dictionary, flatten it to a standard string
                if 'dtype' in obj and isinstance(obj['dtype'], dict):
                    obj['dtype'] = obj['dtype'].get('config', {}).get('name', 'float32')
                for k, v in obj.items():
                    flatten_dtype(v)
            elif isinstance(obj, list):
                for item in obj:
                    flatten_dtype(item)
                    
        flatten_dtype(model_dict)
        # Remove explicit InputLayer to match legacy .h5 topology
        if 'config' in model_dict and 'layers' in model_dict['config']:
            layers = model_dict['config']['layers']
            if len(layers) > 0 and layers[0].get('class_name') == 'InputLayer':
                layers.pop(0)

        json_config_fixed = json.dumps(model_dict)
        
        # Load the sanitized model configuration
        model_ann_loaded = model_from_json(json_config_fixed)
        model_ann_loaded.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])
        model_ann_loaded.load_weights(weights_file, by_name=True)

        label_encoder = LabelEncoder()
        Y_train_encoded = label_encoder.fit_transform(Y_train)
        Y_test_encoded = label_encoder.transform(Y_test)
        Y_test_pred_loaded = model_ann_loaded.predict(X_test[2500:2510, ])
        Y_test_pred_labels = np.argmax(Y_test_pred_loaded, axis=1)
        Y_test_pred_final = label_encoder.inverse_transform(Y_test_pred_labels)

        print("Predictions from loaded model: ", Y_test_pred_final)

    def send_signed_transaction(self, build_transaction):
        try:
            signed_txn = self.web3.eth.account.sign_transaction(build_transaction, self.private_key)
        except:
            raise Exception("Couldn't sign the transaction" + str(build_transaction))
        try:
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        except:
            raise Exception("Couldn't send the transaction")
        self.nonce += 1

        return tx_hash

    def report_threat(self, ip):
        tx_data = self.my_contract.functions.reportThreat(ip).build_transaction(
            {'from': self.eth_address, 'nonce': self.nonce})
        if tx_data is not None:
            self.send_signed_transaction(tx_data)

    def get_block_events(self, latestblock):
        # Ths function gets a new block from the blockchain and gets some of its information
        try:
            block = self.web3.eth.get_block('latest')
        except:
            print("Unable to check the last block, trying again in 5 seconds")
            block = None
        if block is not None:
            blocknumber = block['number']
        else:
            blocknumber = None
        if blocknumber is not None and blocknumber != latestblock:
            print("\nLatest block:", blocknumber)
            latestblock = blocknumber
            event_filter = self.my_contract.events.ThreatReported.create_filter(fromBlock=self.web3.to_hex(blocknumber))
            return event_filter, latestblock
        return None, latestblock

    def wait_for_threats(self):
        latestblock = -1
        print("Waiting for Threat Intelligence updates...")
        while True:
            try:
                block_events, latestblock = self.get_block_events(latestblock)
            except:
                pass
            if block_events is not None:
                try:
                    new_events = block_events.get_all_entries()
                except:
                    pass
                for event in new_events:
                    event = dict(event)
                    info = dict(event['args'])
                    print(f"New threat reported! IP: {info['ip']} by {info['reporter']} at block {event['blockNumber']}")
                    return info["ip"]

    def init_stats(self, info):
        print("I'm the SDN, this is what i've received: " + str(info))
        self.private_key = info['private_key']
        self.eth_address = info['address']
        try:
            self.web3 = Web3(Web3.HTTPProvider(info['eth_node']))
        except:
            raise Exception("Communication with Web3 went wrong")

        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.contract_path = info["contract_name"] + ".sol"
        self.contract_name = info["contract_name"]
        abi_path = ""  # info['path']
        with open(abi_path + self.contract_path, "r") as file:
            contact_list_file = file.read()
        compiled_sol = compile_standard(
            {
                "language": "Solidity",
                "sources": {self.contract_path: {"content": contact_list_file}},
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
        self.contract_abi = \
        json.loads(compiled_sol["contracts"][self.contract_path][self.contract_name]["metadata"])["output"]["abi"]

        self.contract_address = Web3.to_checksum_address(info['contract_address'])
        self.my_contract = self.web3.eth.contract(abi=self.contract_abi, address=self.contract_address)

        self.nonce = self.web3.eth.get_transaction_count(self.eth_address)
        self.configured = True
        if self.role == "consumer":
            process2 = threading.Thread(target=SDN_Controller.wait_for_threats, name="Event_listener")
            process2.start()

    def run(self):
        while not self.configured:
            pass
        if self.role == "producer":
            self.run_model("model_ann_architecture.json", "model_ann.weights.h5")
            # Example: Report a detected attacker IP to the federation
            attacker_ip = "192.168.1.100" 
            try:
                self.report_threat(attacker_ip)
            except:
                pass
            while True:
                pass
        elif self.role == "consumer":
            threat_ip = self.wait_for_threats()
            print(f"Applying mitigation for shared IoC: {threat_ip}")
            while True:
                pass

    def get_port_number(self):
        return self.port_num


if __name__ == "__main__":
    port = input("Choose the port number: ")
    role = input("Choose the role producer/consumer: ")
    SDN_Controller = SDN_Controller(port, role)
    process1 = threading.Thread(target=SDN_api.init, args=(SDN_Controller,), name="SDN_api_thread", daemon=True)
    process1.start()
    SDN_Controller.run()
