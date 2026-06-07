// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title AgentDecisionRegistry
/// @notice Minimal Mantle anchor for AI agent decisions and outcomes.
contract AgentDecisionRegistry {
    struct Decision {
        address reporter;
        bytes32 agentId;
        bytes32 decisionHash;
        string uri;
        uint64 createdAt;
    }

    struct Outcome {
        bytes32 outcomeHash;
        string uri;
        uint64 createdAt;
    }

    Decision[] private _decisions;
    mapping(uint256 => Outcome) private _outcomes;

    event DecisionRecorded(
        uint256 indexed id,
        bytes32 indexed agentId,
        bytes32 indexed decisionHash,
        address reporter,
        string uri
    );
    event OutcomeRecorded(
        uint256 indexed id,
        bytes32 indexed outcomeHash,
        address reporter,
        string uri
    );

    function recordDecision(
        bytes32 agentId,
        bytes32 decisionHash,
        string calldata uri
    ) external returns (uint256 id) {
        require(agentId != bytes32(0), "agentId required");
        require(decisionHash != bytes32(0), "decisionHash required");

        id = _decisions.length;
        _decisions.push(
            Decision({
                reporter: msg.sender,
                agentId: agentId,
                decisionHash: decisionHash,
                uri: uri,
                createdAt: uint64(block.timestamp)
            })
        );

        emit DecisionRecorded(id, agentId, decisionHash, msg.sender, uri);
    }

    function recordOutcome(
        uint256 id,
        bytes32 outcomeHash,
        string calldata uri
    ) external {
        require(id < _decisions.length, "unknown decision");
        require(outcomeHash != bytes32(0), "outcomeHash required");
        require(_outcomes[id].createdAt == 0, "outcome already recorded");

        _outcomes[id] = Outcome({
            outcomeHash: outcomeHash,
            uri: uri,
            createdAt: uint64(block.timestamp)
        });

        emit OutcomeRecorded(id, outcomeHash, msg.sender, uri);
    }

    function decisionCount() external view returns (uint256) {
        return _decisions.length;
    }

    function decision(uint256 id) external view returns (Decision memory) {
        require(id < _decisions.length, "unknown decision");
        return _decisions[id];
    }

    function outcome(uint256 id) external view returns (Outcome memory) {
        require(id < _decisions.length, "unknown decision");
        return _outcomes[id];
    }
}

