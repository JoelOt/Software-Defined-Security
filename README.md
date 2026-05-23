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
│   ├── deploy.py                  # Deployment script (Web3.py)
│   ├── start_geth.sh              # Automated Geth PoA node startup
│   ├── stop_geth.sh               # Stop/clean the Geth node
│   ├── data/                      # Chain data & keystore (gitignored)
│   └── contract_data.json         # Deployed address + ABI (gitignored)
├── sdn/
│   ├── federated_controller.py    # Symmetric Ryu application
│   └── utils.py                   # Blockchain helper functions
├── network/
│   ├── topology_setup.py          # Dynamic Mininet script
│   ├── federation_tunnel.sh       # GRE tunnel script
│   └── snort/                     # Quarantine VNF configuration
│       ├── snort.lua              # Snort 3 config
│       ├── snort.conf             # Snort 2 config (legacy)
│       ├── local.rules            # Detection rules (v2 & v3 compatible)
│       ├── start_snort.sh         # Auto-detect version & launch
│       └── logs/                  # Runtime alert logs (gitignored)
├── attacks/
│   └── ddos_attack.py             # Scapy-based traffic generator
├── .env.example                   # Environment variables template
├── requirements.txt               # Python dependencies
└── README.md
```

## 🛠️ Prerequisites & Dependencies
The following software must be installed on your systems (both VMs, if testing in a federated manner):
*   **Python 3.10+**
*   **Mininet & Open vSwitch (OVS)** (Data Plane)
*   **Ryu SDN Framework** (Control Plane)
*   **Docker** (for running the Geth PoA node)
*   **Snort 2.x or Snort 3** (Security VNF — the start script auto-detects the version)

## ⚙️ Setup & Installation
1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd project/code
    ```
2.  **Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **Install the required Python packages:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure Environment Variables:**
    Copy the provided example file to create your local `.env`:
    ```bash
    cp .env.example .env
    ```
    *Update the `.env` variables if necessary (e.g., set the `CONTRACT_ADDRESS` after deploying the smart contract).*

## 🚀 Execution Instructions

*Note: In a true federated setup, Domain A and Domain B reside on different VMs. Adjust IP addresses according to your setup.*

### Step 1: Initialize the Trust Plane (Geth PoA)
Start the private Go-Ethereum (Geth) Proof-of-Authority node using the automated startup script.
The script creates a sealer account, generates `genesis.json`, initializes the chain, and launches the Docker container — all in one step.

> **Note:** The Geth configuration (container name, Docker image, chain period, etc.) is read from your `.env` file. See `.env.example` for all available options.

```bash
# Start the Geth PoA node (first run creates everything automatically)
blockchain/start_geth.sh
```

Deploy the Smart Contract:
```bash
python3 blockchain/deploy.py
# The deployment script automatically saves the address and ABI to blockchain/contract_data.json.
# You can also manually add it to your .env file as CONTRACT_ADDRESS.
```

To stop or reset the blockchain:
```bash
blockchain/stop_geth.sh          # Stop the container (preserves chain data)
blockchain/stop_geth.sh --clean  # Stop AND wipe all data (full reset)
```

### Step 2: Establish the Data Plane (Mininet)
Launch the dynamic topologies. Mininet must be running before the tunnel can be created because it creates the OVS switch instances.
If running both domains on the same VM, provide the `--domain-code` parameter to prevent virtual interface overlaps (e.g., `ha1-eth0` vs `hb1-eth0`).
```bash
# Terminal 5 (Domain A): 10 hosts starting at 10.0.1.1
# Note: use `sudo -E` to preserve your environment variables (like .env config)
sudo -E python3 network/topology_setup.py --num-hosts 10 --base-ip 10.0.1.0/24 --domain-code a --controller-port 6633

# Terminal 6 (Domain B): 5 hosts starting at 10.0.2.1
sudo -E python3 network/topology_setup.py --num-hosts 5 --base-ip 10.0.2.0/24 --domain-code b --controller-port 6653
```

### Step 3: Start the Quarantine VNF (Snort)
Launch Snort on the dummy interface attached to the source domain's switch. The start script auto-detects whether you have Snort 2 or 3 installed.
```bash
# Terminal 8 (Domain A - Source Domain)
# Snort listens on the sa1-snort dummy interface for redirected attacker traffic
sudo bash network/snort/start_snort.sh sa1
```
You can monitor alerts in real-time:
```bash
tail -f network/snort/logs/alert_fast.txt
```

### Step 4: Start the Control Plane (Ryu)
Launch the symmetric controller for both domains.

*Note: If you have not initialized the Geth trust plane, you can run the controllers in mock mode by prefixing the commands with `USE_TEST_DLT=1`.*

```bash
# Terminal 3 (Controller A - Source Domain)
LOCAL_SUBNET_PREFIX="10.0.1." PYTHONPATH=. ryu-manager sdn/federated_controller.py --ofp-tcp-listen-port 6633

# Terminal 4 (Controller B - Victim Domain)
# If testing on the same machine, use a secondary port (e.g., 6653)
LOCAL_SUBNET_PREFIX="10.0.2." PYTHONPATH=. ryu-manager sdn/federated_controller.py --ofp-tcp-listen-port 6653
```

### Step 5: Establish the Federation Tunnel
The tunnel script connects the two OVS switches via GRE or local Patch Ports. This must be executed bidirectionally on both VMs (or once on the same VM if testing locally).
*Note: Because we used `--domain-code`, the switch names are `sa1` and `sb1` instead of `s1`.*

**Option A: Different VMs (GRE Tunnel)**
```bash
# Terminal 7 (Domain A -> Domain B)
sudo bash network/federation_tunnel.sh 192.168.1.10 192.168.1.11 sa1

# Terminal 8 (Domain B -> Domain A)
sudo bash network/federation_tunnel.sh 192.168.1.11 192.168.1.10 sb1
```

**Option B: Same VM (Local Patch Port)**
```bash
# Terminal 7
# Usage: ./federation_tunnel.sh <LOCAL_IP> <LOCAL_IP> <LOCAL_SWITCH> <REMOTE_SWITCH>
# You only need to run this once!
sudo bash network/federation_tunnel.sh 127.0.0.1 127.0.0.1 sa1 sb1
```

### Step 6: Distributed Attack Simulation
Simulate a botnet by launching the attack from multiple hosts in Domain A targeting Domain B.
```text
mininet-A> ha1 python3 attacks/ddos_attack.py --target 10.0.2.10 & ha2 python3 attacks/ddos_attack.py --target 10.0.2.10 & ha3 python3 attacks/ddos_attack.py --target 10.0.2.10 &
```

**Workflow Results:**
1.  **Detection:** Controller B detects pps spike and drops packets.
2.  **Publication:** Controller B logs IoC to Geth as `Pending`.
3.  **Containment:** Controller A identifies local IPs, triggers SFC to Snort VNF, and updates Geth to `Quarantined`.
4.  **Verification:** `tail -f network/snort/logs/alert_fast.txt` shows alerts — proof that traffic was redirected to the VNF.
5.  **Recovery:** Controller B clears local `DROP` rules; Domain B resumes normal operations.