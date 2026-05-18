#!/bin/bash

# Execute the Geth command and capture the address

# ETHERBASE NODE 1
address=$(geth --datadir node1 account new --password password.txt 2>&1 | grep "Public address of the key" | awk '{print $NF}')
# Create or overwrite the .env file and save the address in it
echo "ETHERBASE_NODE_1=$address" >> .env
echo "$address"

# ETHERBASE NODE 2
address=$(geth --datadir node2 account new --password password.txt 2>&1 | grep "Public address of the key" | awk '{print $NF}')
# Create or overwrite the .env file and save the address in it
echo "ETHERBASE_NODE_2=$address" >> .env
echo "$address"

# ETHERBASE NODE 3
address=$(geth --datadir node3 account new --password password.txt 2>&1 | grep "Public address of the key" | awk '{print $NF}')
# Create or overwrite the .env file and save the address in it
echo "ETHERBASE_NODE_3=$address" >> .env
echo "$address"

# ETHERBASE NODE 4
address=$(geth --datadir node4 account new --password password.txt 2>&1 | grep "Public address of the key" | awk '{print $NF}')
# Create or overwrite the .env file and save the address in it
echo "ETHERBASE_NODE_4=$address" >> .env
echo "$address"






