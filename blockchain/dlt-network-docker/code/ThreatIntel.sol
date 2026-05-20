// SPDX-License-Identifier: MIT
pragma solidity ^0.8.12;

/**
 * @title ThreatIntel
 * @dev Trust Plane component: Smart Contract for sharing Indicators of Compromise (IoCs).
 */
contract ThreatIntel {

    enum Status { None, Pending, Quarantined }

    struct Threat {
        address reporter;
        uint256 timestamp;
        Status status;
    }

    mapping(string => Threat) public threats;

    event ThreatReported(string ip, address reporter, uint256 timestamp);
    event StatusUpdated(string ip, Status newStatus, address updater, uint256 timestamp);

    /**
     * @dev Called by Domain B (Victim) when telemetry spikes.
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
     * @dev Called by Domain A (Source) to confirm quarantine or Domain B to clear.
     */
    function updateStatus(string memory ip, Status newStatus) external {
        require(threats[ip].status != Status.None, "Threat does not exist");
        require(threats[ip].status != newStatus, "Status is already set");

        threats[ip].status = newStatus;
        threats[ip].timestamp = block.timestamp;

        emit StatusUpdated(ip, newStatus, msg.sender, block.timestamp);
    }

    function getThreatStatus(string memory ip) external view returns (Status) {
        return threats[ip].status;
    }
}