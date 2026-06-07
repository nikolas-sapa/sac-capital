# Turing Test Hackathon Winning Plan

## Verdict

The current repo is not submission-ready for this hackathon. It is a solid off-chain paper-trading and research system, but the brief rewards Mantle deployment, on-chain verifiability, a public frontend, and an easy judge narrative. Today those pieces are missing.

The best path is not to pitch a generic Polymarket bot. The winning direction should be:

> Verifiable AI agent benchmark for prediction-market decisions on Mantle.

Use the existing bot as the decision engine, then anchor every AI decision and later outcome on Mantle through `AgentDecisionRegistry`.

## Track Choice

Primary track: `AI Alpha & Data`

Why:

- Existing repo already has LLM probability estimates, market scanning, ledgers, calibration-oriented stats, and paper execution.
- The track explicitly rewards data quality, AI analysis depth, technical completeness, visualization quality, verifiability, backtesting, live/paper records, and on-chain records.
- This avoids the heavier Byreal/RealClaw dependency required by Agentic Economy.

Secondary awards to target:

- `20 Project Deployment Award`
- `Best UI/UX Award`
- `Community Voting`

## Current Assets

- Polymarket runner: `runner.py`
- Polymarket strategies: `strategies/llm_probability`, `strategies/weather`, `strategies/crypto_updown`
- Paper execution and ledger: `core/execution/paper.py`, `core/ledger.py`
- Strategy allocation and performance: `orchestrator/allocator.py`, `orchestrator/performance.py`
- Equity research artifacts and replay infrastructure: `equities/research`, `equities/eval`
- macOS local deployment: `deploy/`
- Regression suite: `tests/`

## Critical Gaps

- No Mantle deployment workflow.
- No verified deployed smart contract.
- No frontend demo.
- No wallet or Web3 integration.
- No Mantle on-chain data source.
- No on-chain callable AI-powered function before this plan.
- No public deployment target.
- README still positions the repo as paper-only local research, not a hackathon submission.
- Live Polymarket scans are blocked on this machine without VPN, per `deploy/README.md`.

## Implemented First Step

This plan adds the first concrete verifiability layer:

- `contracts/AgentDecisionRegistry.sol`
- `hackathon/verifiability.py`
- `scripts/export_mantle_commitments.py`
- `tests/test_hackathon_verifiability.py`

The exporter converts existing ledger rows and research artifacts into deterministic `bytes32` hashes. The contract records those hashes and outcome hashes on Mantle.

## Build Plan

### P0: Qualify For Deployment Award

1. Add a Foundry or Hardhat project for `contracts/AgentDecisionRegistry.sol`.
2. Deploy to Mantle Sepolia testnet first.
3. Verify the contract on Mantle Explorer.
4. Export current decision hashes:
   ```sh
   ./.venv/bin/python scripts/export_mantle_commitments.py --out data/mantle_commitments.jsonl
   ```
5. Write a deployment script that submits at least one real exported decision hash to `recordDecision`.
6. Publish the JSONL payload so judges can recompute the hash.

### P1: Build Judge-Facing Frontend

Create a small frontend that shows:

- Agent identity
- Latest AI decisions
- On-chain transaction/hash status
- Market question, fair probability, price, confidence, edge, reasoning
- Outcome and PnL once resolved
- A recompute-hash button or displayed canonical JSON

Recommended stack: Next.js or Vite with wagmi/viem. The repo currently has no frontend, so keep it narrow.

### P2: Make Mantle Core To The Story

Add one Mantle data source so the project is not merely storing hashes on Mantle:

- Query the deployed registry events from Mantle RPC.
- Compute an agent reputation score from on-chain decisions/outcomes.
- Show the score in the frontend.

This makes Mantle the benchmark and reputation layer.

### P3: Demo Narrative

Demo flow:

1. Agent scans prediction markets.
2. AI estimates probability and produces a reasoned decision.
3. Bot writes local auditable payload.
4. Exporter hashes the payload.
5. Frontend submits the hash to Mantle.
6. Judges inspect Mantle Explorer and recompute the hash.
7. Later outcome is anchored and reputation updates.

## File-Level Work Remaining

- `pyproject.toml`: add any Web3/deployment helper dependencies only if used.
- `contracts/`: add Foundry/Hardhat config and deployment scripts.
- `frontend/`: build the public demo UI.
- `README.md`: add hackathon pitch, deployment address, demo link, video link, and reproduction steps.
- `.env.example`: add Mantle RPC, private key, contract address, public artifact URL.
- `scripts/`: add deploy/submit scripts for Mantle transactions.
- `tests/`: add contract tests and exporter integration tests.

## Blockers

- Need Mantle RPC endpoint.
- Need deployer wallet private key funded with testnet MNT.
- Need decision about where to host the frontend.
- Need public storage for exported JSONL payloads.
- Need VPN or alternate environment for live Polymarket scans.

