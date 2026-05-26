// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title ThreatIntel
 * @dev Trust Plane component: Smart Contract for sharing Indicators of Compromise (IoCs)
 *      across independent network domains in the federated SDN architecture.
 */
contract ThreatIntel {

    enum Status { None, Pending, Quarantined }

    struct Threat {
        address reporter;
        uint256 timestamp;
        Status status;
    }

    // Stores threats by IP address
    mapping(string => Threat) public threats;

    // Events for the Control Plane (Ryu controllers) to listen for
    event ThreatReported(string ip, address reporter, uint256 timestamp);
    event StatusUpdated(string ip, Status newStatus, address updater, uint256 timestamp);

    /**
     * @dev Called by the Control Plane (Ryu) when a local domain detects a telemetry spike.
     *      Registers the IP as an IoC with 'Pending' status, triggering an event for the federation.
     * @param ip The IP address of the suspected attacker.
     */
    function reportThreat(string memory ip) external {
        require(threats[ip].status == Status.None, "Threat already reported");

        threats[ip] = Threat({
            reporter: msg.sender,
            timestamp: block.timestamp,
            status: Status.Pending
        });

        emit ThreatReported(ip, msg.sender, block.timestamp);
    }

    /**
     * @dev Called by the Control Plane to update the mitigation state of an IoC.
     *      E.g., transitioning to 'Quarantined' once the SFC routing is enforced,
     *      or clearing the status to restore normal operations.
     * @param ip The IP address of the attacker.
     * @param newStatus The updated mitigation status (e.g., Quarantined).
     */
    function updateStatus(string memory ip, Status newStatus) external {
        require(threats[ip].status != Status.None, "Threat does not exist");
        require(threats[ip].status != newStatus, "Status is already set to this value");

        threats[ip].status = newStatus;
        threats[ip].timestamp = block.timestamp; // Update timestamp to reflect latest change

        emit StatusUpdated(ip, newStatus, msg.sender, block.timestamp);
    }

    /**
     * @dev Returns the current mitigation status for an IoC.
     *      Kept explicit for controller/orchestrator integrations that prefer
     *      a small read helper over the generated public mapping accessor.
     * @param ip The IP address to query.
     */
    function getThreatStatus(string memory ip) external view returns (Status) {
        return threats[ip].status;
    }
}
