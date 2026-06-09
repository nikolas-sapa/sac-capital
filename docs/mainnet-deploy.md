# Mantle Mainnet Deployment Guide

This guide covers deploying `AgentDecisionRegistry` to Mantle mainnet and submitting
decisions. The Sepolia testnet deployment (`0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887`)
remains unchanged.

---

## Prerequisites

- Foundry installed (`forge`, `cast`)
- Python environment: `uv sync`
- A dedicated deployer wallet — never reuse a wallet that holds significant funds

---

## Steps

### 1. Fund the deployer wallet

Send at least **0.01 MNT** to the deployer wallet address to cover gas.
You can bridge from Ethereum via https://bridge.mantle.xyz.

### 2. Set environment variables

In your `.env` (never commit this file):

```sh
MANTLE_RPC_URL=https://rpc.mantle.xyz
MANTLE_PRIVATE_KEY=0x<your-deployer-private-key>
MANTLESCAN_API_KEY=<your-mantlescan-api-key>
```

### 3. Run the test suite

Confirm the contract compiles and all tests pass before spending gas:

```sh
forge test
```

### 4. Deploy to mainnet

```sh
forge script contracts/script/DeployMainnet.s.sol \
  --rpc-url https://rpc.mantle.xyz \
  --broadcast \
  --verify
```

The deployed address is printed in the output. Copy it before proceeding.

### 5. Update contract address

Set the new address in `.env` and in the Vercel dashboard:

```sh
# .env
AGENT_REGISTRY_ADDRESS=0x<deployed-address>
```

Vercel env vars to update:
- `VITE_AGENT_REGISTRY_ADDRESS` = `0x<deployed-address>`
- `VITE_MANTLE_RPC_URL` = `https://rpc.mantle.xyz`
- `VITE_MANTLE_EXPLORER_BASE` = `https://explorer.mantle.xyz`

### 6. Submit decisions

Dry-run first to confirm everything looks right:

```sh
./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract <deployed-address> \
  --agent-id mantle-verifiable-polymarket-agent \
  --network mainnet \
  --limit 5
```

Then broadcast (the WARNING is printed to stderr as a reminder):

```sh
./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract <deployed-address> \
  --agent-id mantle-verifiable-polymarket-agent \
  --network mainnet \
  --send \
  --limit 5
```

### 7. Update README

Once deployed, update `README.md` with:
- Mainnet contract address
- Mantlescan explorer link: `https://explorer.mantle.xyz/address/<deployed-address>`
- Deployment transaction hash

---

## Network reference

| Network | RPC | Explorer |
|---------|-----|----------|
| Mantle Sepolia | `https://rpc.sepolia.mantle.xyz` | `https://sepolia.mantlescan.xyz` |
| Mantle Mainnet | `https://rpc.mantle.xyz` | `https://explorer.mantle.xyz` |
