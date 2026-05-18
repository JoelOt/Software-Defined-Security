// SPDX-License-Identifier: MIT
pragma solidity ^0.8.12;
contract SDNContract {

    // Model
    string private model;

    // Enum defining participant roles
    enum Role { SDN, NetworkOrchestrator }

    // Mapping to track registered participants
    mapping(address => Participant) public participant;

    // Struct to represent a participant (SDN, NetworkOrchestrator)
    struct Participant {
        string name;
        bool registered;
        Role role;
    }

    // Event emitted when a participant is registered
    event ParticipantRegistered(address participant, string name);

    // Event emitted when a participant is unregistered
    event ParticipantUnregistered(address participant, string name);

    // Event emitted when a participant is deleted
    event ParticipantDeleted(address participant, string name);

    // Event emitted when a new model has been set
    event ModelSet(address participant, string model);


    // Constructor to initialize the contract and register the NetworkOrchestrator
    constructor() {
        // Set the initial model to an empty string
        model = "";
        // Register the deploying address as an NetworkOrchestrator participant
        participant[msg.sender] = Participant({
                name: "NetworkOrchestrator",
                registered: true,
                role: Role.NetworkOrchestrator
        });
        emit ParticipantRegistered(msg.sender, "NetworkOrchestrator");
    }

    // Function to register a select group of N Agents in the smart contract, can only be called by the NetworkOrchestrator
    function registerAgents(address[] memory agentAddresses, string[] memory agentNames) public {
        // Ensure that only the NetworkOrchestrator calls the function
        require(participant[msg.sender].role==Role.NetworkOrchestrator, "Only the NetworkOrchestrator can register Agents");

        // Loop through the agentAddresses array and register the agents
        for (uint256 i = 0; i < agentAddresses.length; i++) {
            address agentAddress = agentAddresses[i];
            string memory agentName = agentNames[i];

            // Ensure that the agent name is not empty
            require(bytes(agentName).length > 0, "Name is not valid");

            // Ensure that the agent is not already registered
            require(participant[agentAddress].registered == false, "Agent already registered");

            // Register the agent
            participant[agentAddress] = Participant({
                name: agentName,
                registered: true,
                role: Role.SDN
            });

            // Emit the event to notify the registration of the agent
            emit ParticipantRegistered(agentAddress, agentName);
        }
    }


    // Function to set the secret key, can only be called by registered participants
    function setModel(string memory new_model) public {
        Participant storage current_participant = participant[msg.sender];
        require(current_participant.registered==true, "Participant is not registered. Can not look into. Please register.");
        model = new_model;
        emit ModelSet(msg.sender, new_model);
    }

    // Function to retrieve the secret key, can only be called by registered participants
    function getModel(address call_address) public view returns (string memory) {
        Participant storage current_participant = participant[call_address];
        require(current_participant.registered == true, "Participant is not registered. Can not look into. Please register.");
        return model;
    }
}
