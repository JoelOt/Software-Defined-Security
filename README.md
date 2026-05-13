# Federated Zero-Trust SDN

## 👥 Team
*   **Angela Fernandez**
*   **Eric Eugenio** 
*   **Joel Otero** 
*   **Miquel Romeo** 

## 🎓 Project Context
This project is developed as part of the **Software-Defined Systems (SDS)** course for the **Master in Cybersecurity at UPC (Universitat Politècnica de Catalunya)**. The primary objective is to solidify the course’s core pillars—**SDN, NFV, DLT, and Network Telemetry**—into a single, cohesive ecosystem. 

The project addresses the challenge of collaborative security between untrusted or independent network domains by proposing a **3-Tier Federated Architecture**:
1.  **Data Plane:** Localized network traffic and virtualized security functions (NFV/Snort).
2.  **Control Plane:** Intelligent SDN management via symmetric controllers.
3.  **Trust Plane:** A decentralized ledger (DLT) for immutable and verifiable distribution of Indicators of Compromise (IoC).

## 🏗️ Architecture & Design
The system utilizes a **Symmetric Controller Design**. Rather than using specialized roles, every domain deploys an identical controller instance designed to fulfill the capabilities of all three architectural layers:
*   **Data Plane Interaction:** Extracts raw flow telemetry to detect volumetric anomalies and enforces Service Function Chaining (SFC) for traffic redirection.
*   **Control Plane Logic:** Translates high-level security "Intents" into OpenFlow rules for immediate local mitigation and subsequent source-side quarantine.
*   **Trust Plane Integration:** Acts as a blockchain participant that validates, publishes, and listens for IoCs via Smart Contracts on a private Ethereum (Geth) network.

## 📂 File Structure
```text
federated-quarantine-sdn/
├── blockchain/
│   ├── ThreatIntel.sol            # Smart Contract (Solidity)
│   └── deploy.py                  # Deployment script (Web3.py)
├── sdn/
│   ├── federated_controller.py    # Symmetric Ryu application
│   └── utils.py                   # Blockchain helper functions
├── network/
│   ├── topology_setup.py          # Dynamic Mininet script
│   └── federation_tunnel.sh       # GRE/VxLAN tunnel script
├── vnfs/
│   └── snort_config/               # IDS rules for quarantine zone
├── attacks/
│   └── ddos_attack.py             # Scapy-based traffic generator
└── README.md
```

## 🚀 Execution Instructions

### Step 1: Initialize the Trust Plane (Geth PoA)
Initialize and start the private Go-Ethereum (Geth) network using Proof of Authority (Clique).
```bash
# Terminal 1: Initialize the blockchain state
geth --datadir ./blockchain/data init blockchain/config/genesis.json

# Start the Geth node
geth --datadir ./blockchain/data --networkid 1337 --http --http.api eth,net,web3 --mine --miner.threads=1
```

Deploy the Smart Contract:
```bash
# Terminal 2
cd blockchain/
python3 deploy.py
# Note the Contract Address and update sdn/utils.py
```

### Step 2: Establish the Data Plane (Mininet)
Set up the inter-VM tunnel and launch the dynamic topologies.
```bash
# Terminal 2: Run tunnel script
sudo bash network/federation_tunnel.sh

# Terminal 3 (Domain A): 10 hosts starting at 10.0.1.1
sudo python3 network/topology_setup.py --num-hosts 10 --base-ip 10.0.1.0/24

# Terminal 4 (Domain B): 5 hosts starting at 10.0.2.1
sudo python3 network/topology_setup.py --num-hosts 5 --base-ip 10.0.2.0/24
```

### Step 3: Start the Control Plane (Ryu)
Launch the symmetric controller for both domains.
```bash
# Terminal 5 (Controller A)
ryu-manager sdn/federated_controller.py --ofp-tcp-listen-port 6633

# Terminal 6 (Controller B)
ryu-manager sdn/federated_controller.py --ofp-tcp-listen-port 6653
```

### Step 4: Distributed Attack Simulation
Simulate a botnet by launching the attack from multiple hosts in Domain A targeting Domain B.
```text
mininet-A> h1 python3 attacks/ddos_attack.py --target 10.0.2.10 & h2 python3 attacks/ddos_attack.py --target 10.0.2.10 & h3 python3 attacks/ddos_attack.py --target 10.0.2.10 &
```

**Workflow Results:**
1.  **Detection:** Controller B detects pps spike and drops packets.
2.  **Publication:** Controller B logs IoC to Geth as `Pending`.
3.  **Containment:** Controller A identifies local IPs, triggers SFC to Snort VNF, and updates Geth to `Quarantined`.
4.  **Recovery:** Controller B clears local `DROP` rules; Domain B resumes normal operations.