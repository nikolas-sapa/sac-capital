// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../AgentDecisionRegistry.sol";

interface Vm {
    function expectEmit(bool checkTopic1, bool checkTopic2, bool checkTopic3, bool checkData) external;
    function expectRevert(bytes memory revertData) external;
}

contract AgentDecisionRegistryTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

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

    AgentDecisionRegistry private registry;
    bytes32 private constant AGENT_ID = keccak256("mantle-verifiable-agent");
    bytes32 private constant DECISION_HASH = keccak256("decision");
    bytes32 private constant OUTCOME_HASH = keccak256("outcome");

    function setUp() public {
        registry = new AgentDecisionRegistry();
    }

    function testRecordsDecision() public {
        uint256 id = registry.recordDecision(AGENT_ID, DECISION_HASH, "ipfs://decision");

        require(id == 0, "unexpected id");
        require(registry.decisionCount() == 1, "unexpected count");

        AgentDecisionRegistry.Decision memory decision = registry.decision(id);
        require(decision.reporter == address(this), "unexpected reporter");
        require(decision.agentId == AGENT_ID, "unexpected agent");
        require(decision.decisionHash == DECISION_HASH, "unexpected hash");
        require(keccak256(bytes(decision.uri)) == keccak256("ipfs://decision"), "unexpected uri");
        require(decision.createdAt > 0, "missing timestamp");
    }

    function testEmitsDecisionRecorded() public {
        vm.expectEmit(true, true, true, true);
        emit DecisionRecorded(0, AGENT_ID, DECISION_HASH, address(this), "ipfs://decision");

        registry.recordDecision(AGENT_ID, DECISION_HASH, "ipfs://decision");
    }

    function testRejectsZeroAgentId() public {
        vm.expectRevert(bytes("agentId required"));
        registry.recordDecision(bytes32(0), DECISION_HASH, "");
    }

    function testRejectsZeroDecisionHash() public {
        vm.expectRevert(bytes("decisionHash required"));
        registry.recordDecision(AGENT_ID, bytes32(0), "");
    }

    function testRecordsOutcome() public {
        uint256 id = registry.recordDecision(AGENT_ID, DECISION_HASH, "ipfs://decision");

        vm.expectEmit(true, true, true, true);
        emit OutcomeRecorded(id, OUTCOME_HASH, address(this), "ipfs://outcome");
        registry.recordOutcome(id, OUTCOME_HASH, "ipfs://outcome");

        AgentDecisionRegistry.Outcome memory outcome = registry.outcome(id);
        require(outcome.outcomeHash == OUTCOME_HASH, "unexpected outcome");
        require(keccak256(bytes(outcome.uri)) == keccak256("ipfs://outcome"), "unexpected uri");
        require(outcome.createdAt > 0, "missing timestamp");
    }

    function testRejectsDuplicateOutcome() public {
        uint256 id = registry.recordDecision(AGENT_ID, DECISION_HASH, "");
        registry.recordOutcome(id, OUTCOME_HASH, "");

        vm.expectRevert(bytes("outcome already recorded"));
        registry.recordOutcome(id, keccak256("other"), "");
    }

    function testRejectsUnknownDecisionIdForOutcome() public {
        vm.expectRevert(bytes("unknown decision"));
        registry.recordOutcome(1, OUTCOME_HASH, "");
    }
}
