#!/bin/bash

# Read environment variables from .env file
source .env

# Define the JSON configuration
json_config='{
  	"config": {
		"chainId": 12345,
		"homesteadBlock": 0,
		"eip150Block": 0,
		"eip155Block": 0,
		"eip158Block": 0,
		"byzantiumBlock": 0,
		"constantinopleBlock": 0,
		"petersburgBlock": 0,
		"istanbulBlock": 0,
		"muirGlacierBlock": 0,
		"berlinBlock": 0,
		"londonBlock": 0,
		"arrowGlacierBlock": 0,
		"grayGlacierBlock": 0,
		"clique": {
			"period": 1,
			"epoch": 30000
		}
	},
	"difficulty": "1",
	"gasLimit": "6721975",
	"extraData": "0x0000000000000000000000000000000000000000000000000000000000000000ETHERBASE_NODE_1ETHERBASE_NODE_2ETHERBASE_NODE_3ETHERBASE_NODE_40000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
	"alloc": {
		"ETHERBASE_NODE_1": { "balance": "10000000000000000000000" },
		"ETHERBASE_NODE_2": { "balance": "10000000000000000000000" },
		"ETHERBASE_NODE_3": { "balance": "10000000000000000000000" },
		"ETHERBASE_NODE_4": { "balance": "10000000000000000000000" }
	}
}'

# Substitute environment variables in the JSON configuration and Remove the "0x" prefix from the Ethereum addresses
json_config=${json_config//ETHERBASE_NODE_1/${ETHERBASE_NODE_1#"0x"}}
json_config=${json_config//ETHERBASE_NODE_2/${ETHERBASE_NODE_2#"0x"}}
json_config=${json_config//ETHERBASE_NODE_3/${ETHERBASE_NODE_3#"0x"}}
json_config=${json_config//ETHERBASE_NODE_4/${ETHERBASE_NODE_4#"0x"}}

# Save the JSON configuration to a file
echo "$json_config" > genesis.json