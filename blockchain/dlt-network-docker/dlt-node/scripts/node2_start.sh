#!/bin/bash

# Execute the geth init command to initialize the data directory with genesis.json
output=$(geth init --datadir node2 genesis.json)
echo "$output"

# Read environment variables from .env file
#source .env

# Define the command
#command="geth --identity "node2" --syncmode "full" --ws --ws.addr $IP_NODE_2 --ws.port $WS_PORT_NODE_2 --datadir node2 --port $ETH_PORT_NODE_2 --bootnodes $BOOTNODE_URL --ws.api "eth,net,web3,personal,miner,admin" --networkid 1234 --nat "any" --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_2 --ipcdisable --unlock $ETHERBASE_NODE_2 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_2"
command="geth --identity "node2" --syncmode "full" --http --http.vhosts=geth-proxy --http.addr $IP_NODE_2 --http.port $WS_PORT_NODE_2 --datadir node2 --port $ETH_PORT_NODE_2 --bootnodes $BOOTNODE_URL --http.api "eth,net,web3,personal,miner,admin" --networkid 1234 --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_2 --ipcdisable --unlock $ETHERBASE_NODE_2 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_2"

# Execute the command
eval $command
