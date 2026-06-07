# Mantle Contract Stack

`AgentDecisionRegistry.sol` is the minimum on-chain primitive this repo needs for the Turing Test hackathon:

- `recordDecision(bytes32 agentId, bytes32 decisionHash, string uri)` anchors an AI decision hash on Mantle.
- `recordOutcome(uint256 id, bytes32 outcomeHash, string uri)` anchors the later result.
- `uri` should point to the public JSONL payload exported by `scripts/export_mantle_commitments.py`.

This is not deployed yet. To qualify for the deployment award, deploy this contract to Mantle testnet or mainnet, verify it on Mantle Explorer, and include the address in the DoraHacks submission.

## Local Contract Tests

Install Foundry, then run:

```sh
forge test
```

The tests cover decision recording, event emission, zero-value rejections, outcome recording, duplicate outcome rejection, and unknown decision rejection.

## Deploy To Mantle

Set a dedicated deployer key in `.env` or the shell. Do not use a wallet that holds unrelated funds.

```sh
export MANTLE_RPC_URL=https://rpc.sepolia.mantle.xyz
export MANTLE_PRIVATE_KEY=0x...

forge script contracts/script/DeployAgentDecisionRegistry.s.sol \
  --rpc-url "$MANTLE_RPC_URL" \
  --broadcast
```

After deployment, set:

```sh
export AGENT_REGISTRY_ADDRESS=0x...
```

## Verify On Mantle Explorer

Use the matching Mantle Explorer verifier for the network you deployed to:

```sh
forge verify-contract "$AGENT_REGISTRY_ADDRESS" \
  contracts/AgentDecisionRegistry.sol:AgentDecisionRegistry \
  --chain-id 5003 \
  --verifier blockscout \
  --verifier-url https://explorer.sepolia.mantle.xyz/api
```

If the explorer URL changes, use the current Mantle Explorer verification endpoint and record the final verification link in the DoraHacks submission.

## Submit A Decision Hash

Dry-run first:

```sh
./.venv/bin/python scripts/export_mantle_commitments.py \
  --ledger data/ledger.db \
  --out data/mantle_commitments.jsonl

./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract "$AGENT_REGISTRY_ADDRESS" \
  --agent-id "$AGENT_ID" \
  --limit 1
```

Broadcast only when the RPC URL, deployer key, and contract address are correct:

```sh
./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract "$AGENT_REGISTRY_ADDRESS" \
  --agent-id "$AGENT_ID" \
  --limit 1 \
  --send
```
