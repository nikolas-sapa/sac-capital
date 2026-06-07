// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../AgentDecisionRegistry.sol";

interface Vm {
    function envUint(string memory name) external view returns (uint256);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

contract DeployAgentDecisionRegistry {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (AgentDecisionRegistry registry) {
        uint256 deployerKey = vm.envUint("MANTLE_PRIVATE_KEY");
        vm.startBroadcast(deployerKey);
        registry = new AgentDecisionRegistry();
        vm.stopBroadcast();
    }
}
