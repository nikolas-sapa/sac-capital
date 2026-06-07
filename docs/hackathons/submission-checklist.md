# Turing Test Hackathon Submission Checklist

## DoraHacks Fields

- Project title: `Mantle-Verifiable AI Prediction Agent Benchmark`
- One-line pitch: `AI prediction-market decisions are exported as deterministic bytes32 commitments and anchored on Mantle for public verification and reputation.`
- Description: explain the paper-trading agent, deterministic payload exporter, Mantle `AgentDecisionRegistry`, frontend verification panel, and outcome/reputation loop.
- Repo URL: `https://github.com/nikolas-sapa/sapa_fund`
- Demo URL: `https://sapa-fund.vercel.app`
- Video URL: `TODO`
- Contract address: `0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887`
- Contract explorer URL: `https://explorer.sepolia.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887`
- Deployment transaction: `https://explorer.sepolia.mantle.xyz/tx/0x62b7b9ce6c469768fc979f2d00610a7aba39b71c48a55a0081fdca424e4efe4b`
- Decision transaction: `https://explorer.sepolia.mantle.xyz/tx/0x94ac5787a23f472a9d97e3ca435b9dc4818b734e0b3efad9ad2d2fd1251c6076`
- Explorer verification URL: `https://explorer.sepolia.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887#code`
- Team info: `TODO`

## Deployment Award Checklist

- Smart contract deployed on Mantle mainnet or testnet.
- Contract verified on Mantle Explorer.
- At least one exported AI decision submitted through `recordDecision`.
- Public frontend demo accessible.
- Deployment address included in DoraHacks.
- Demo video is at least 2 minutes.
- GitHub repo is public and includes README reproduction steps.

## Best UI/UX Checklist

- First screen says `Mantle-Verifiable AI Prediction Agent`.
- One-line pitch is visible without scrolling.
- Decision feed shows question, strategy, probability, price, confidence, reason, and hash.
- Mantle section shows contract address, explorer link, and latest registry events or a clearly labeled fallback.
- Verification panel shows canonical JSON and recomputed hash.
- Mobile layout has no overlapping text or clipped buttons.

## AI Alpha & Data Scoring Checklist

- AI decision payloads include market question, strategy, fair probability, confidence, and reason.
- Exporter produces deterministic canonical JSON and `bytes32` hashes.
- Mantle registry is the reputation layer, not decorative storage.
- Outcomes can be recorded later with `recordOutcome`.
- README states paper-only safety boundary and no live custody/trading authority.

## Demo Script Checklist

- Show bot/ledger source data.
- Run exporter and show `data/mantle_commitments.jsonl`.
- Submit one hash to Mantle or show exact dry-run if credentials are unavailable.
- Open Mantle Explorer contract page.
- Open frontend and recompute the selected payload hash.
- Explain how outcome hashes produce verifiable agent scoring over time.

## Final Pre-Submit Commands

```sh
./.venv/bin/python -m pytest
./.venv/bin/python scripts/export_mantle_commitments.py --ledger data/ledger.db --out data/mantle_commitments.jsonl
./.venv/bin/python scripts/submit_mantle_decisions.py --commitments data/mantle_commitments.jsonl --contract "$AGENT_REGISTRY_ADDRESS" --agent-id "$AGENT_ID" --limit 1
forge test
cd frontend && npm install && npm run build
```

Only run the real submission command with `--send` after confirming `MANTLE_RPC_URL`, `MANTLE_PRIVATE_KEY`, and `AGENT_REGISTRY_ADDRESS`.
