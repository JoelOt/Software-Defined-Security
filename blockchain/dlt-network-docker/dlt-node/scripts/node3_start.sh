#!/bin/bash

# Execute the geth init command to initialize the data directory with genesis.json
output=$(geth init --datadir node3 genesis.json)
echo "$output"

# Read environment variables from .env file
# source .env

# Define the command
#command="geth --identity "node3" --syncmode "full" --ws --ws.addr $IP_NODE_3 --ws.port $WS_PORT_NODE_3 --datadir node3 --port $ETH_PORT_NODE_3 --bootnodes $BOOTNODE_URL --ws.api "eth,net,web3,personal,miner,admin" --networkid 1234 --nat "any" --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_3 --ipcdisable --unlock $ETHERBASE_NODE_3 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_3"
command="geth --identity "node3" --syncmode "full" --http --http.vhosts=geth-proxy --http.addr $IP_NODE_3 --http.port $WS_PORT_NODE_3 --datadir node3 --port $ETH_PORT_NODE_3 --bootnodes $BOOTNODE_URL --http.api "eth,net,web3,personal,miner,admin" --networkid 1234 --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_3 --ipcdisable --unlock $ETHERBASE_NODE_3 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_3"

# Execute the command
eval $command
