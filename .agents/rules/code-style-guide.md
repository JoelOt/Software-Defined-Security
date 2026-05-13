---
trigger: always_on
---

# Federated SDN Project Coding Standards

You are the lead developer for the UPC Master in Cybersecurity SDS Project. 
Follow these strict architectural and stylistic rules for every code generation task.

## 1. General Style Guidelines
- **Language:** English.
- **Indentation:** 4 spaces for Python/Bash, 2 spaces for Solidity.
- **Naming:** 
  - Python: `snake_case` for variables/functions, `PascalCase` for classes.
  - Solidity: `mixedCase` for variables/functions, `PascalCase` for contracts.
- **Documentation:** Every function must have a brief docstring explaining its role in the 3-tier architecture (Data, Control, or Trust).

## 2. Python (Ryu & Mininet) Specifics
- **OpenFlow Version:** Strictly use OpenFlow 1.3 (`ofproto_v1_3`).
- **Asynchronous Safety:** Ryu uses `eventlet`. Do NOT use blocking `time.sleep()`; use `hub.sleep()`. 
- **DLT Calls:** All `web3.py` calls must be wrapped in `hub.spawn()` or handled via non-blocking methods to prevent freezing the OpenFlow event loop.
- **Logging:** Use the native Ryu logger (`self.logger.info`, `self.logger.error`). Do not use `print()`.
- **Boilerplate:** Always include the standard Ryu imports and class inheritance:
  ```python
  from ryu.base import app_manager
  from ryu.controller import ofp_event
  from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
  from ryu.ofproto import ofproto_v1_3
  ```

## 3. Trust Plane (Solidity) Specifics
- **Compiler:** `pragma solidity ^0.8.0;`
- **Efficiency:** Optimize for gas. Use `uint256` where possible and avoid expensive string concatenations on-chain.
- **Events:** Every IoC update (`Pending`, `Quarantined`) MUST emit an event for the Ryu listeners to catch.

## 4. Architectural Logic (The "Hold & Release" Loop)
When writing logic for `federated_controller.py`, ensure the following sequence is respected:
1. **Detection:** Telemetry spike -> Local `OFP_DROP`.
2. **Notification:** Publish IoC to DLT as `Pending`.
3. **SFC Quarantine:** If DLT event is local IP -> Redirect to VNF port (Snort).
4. **Restoration:** If DLT state is `Quarantined` -> Delete local `DROP` rule.

## 5. Directory Context
Always assume the following structure for imports and file paths:
- Controllers: `/sdn`
- Topologies: `/network`
- Contracts: `/blockchain`
- Attacks: `/attacks`