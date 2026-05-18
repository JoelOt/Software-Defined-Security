#!/bin/bash

# Execute the geth init command to initialize the data directory with genesis.json
output=$(geth init --datadir node1 genesis.json)
echo "$output"

# Read environment variables from .env file
#source .env

# Define the command
#command="geth --identity "node1" --syncmode "full" --ws --ws.addr $IP_NODE_1  --ws.port $WS_PORT_NODE_1 --datadir node1 --port $ETH_PORT_NODE_1 --bootnodes $BOOTNODE_URL --ws.api "eth,net,web3,personal,miner,admin" --networkid 1234 --nat "any" --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_1 --ipcdisable --unlock $ETHERBASE_NODE_1 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_1"
# command="geth --identity "node1" --syncmode "full" --netrestrict $DLT_SUBNET --http --http.vhosts=geth-proxy --http.addr $IP_NODE_1  --http.port $WS_PORT_NODE_1 --http.corsdomain '*' --datadir node1 --port $ETH_PORT_NODE_1 --bootnodes $BOOTNODE_URL --http.api "eth,net,web3,personal,miner,admin" --networkid 1234 --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_1 --ipcdisable --unlock $ETHERBASE_NODE_1 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_1"
command="geth --identity "node1" --syncmode "full" --netrestrict $DLT_SUBNET --http --http.vhosts=geth-proxy --http.addr $IP_NODE_1  --http.port $WS_PORT_NODE_1 --http.corsdomain '*' --datadir node1 --port $ETH_PORT_NODE_1 --bootnodes $BOOTNODE_URL --http.api "eth,net,web3,personal,miner,admin" --networkid 1234 --allow-insecure-unlock --authrpc.port $RPC_PORT_NODE_1 --ipcdisable --unlock $ETHERBASE_NODE_1 --password password.txt --mine --snapshot=false --miner.etherbase $ETHERBASE_NODE_1 --ws --ws.addr $IP_NODE_1  --ws.port 8555 --ws.origins '*' --ws.api "eth,net,web3,personal,miner,admin""

# Execute the command
eval $command
