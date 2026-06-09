// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Run with:
//   forge script contracts/script/DeployMainnet.s.sol \
//     --rpc-url https://rpc.mantle.xyz \
//     --broadcast \
//     --verify

import "../AgentDecisionRegistry.sol";

interface Vm {
    function envUint(string memory name) external view returns (uint256);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

contract DeployMainnet {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (AgentDecisionRegistry registry) {
        uint256 deployerKey = vm.envUint("MANTLE_PRIVATE_KEY");
        vm.startBroadcast(deployerKey);
        registry = new AgentDecisionRegistry();
        vm.stopBroadcast();

        // solhint-disable-next-line no-console
        emit log_named_address("AgentDecisionRegistry deployed at", address(registry));
    }

    event log_named_address(string key, address val);
}
