# DoraHacks Copy — Paste Ready

---

## DETAILS SCREEN

### Project Name
SAC Capital

### One-line Pitch
AI trading decisions anchored on Mantle as bytes32 commitments — anyone can verify what the agent decided before the outcome was known.

### Project Description
AI trading agents are black boxes. They publish returns but not reasoning. Theses get rewritten after the fact, win rates get cherry-picked, and there is no protocol-level mechanism for an agent to prove it made a decision before the outcome resolved.

SAC Capital is a multi-stage AI trading agent that makes every decision cryptographically verifiable on Mantle. Before any order is placed, the full decision payload (strategy, confidence, thesis, risk parameters) is serialized to canonical JSON and hashed to bytes32 via SHA-256. This hash is recorded in AgentDecisionRegistry on Mantle Mainnet — before the trade is placed, before the result is known.

The pipeline runs in five stages: deterministic equity screen, Haiku pre-filter, Sonnet bull analyst, Sonnet challenger, Auditor. Only decisions that survive all five stages reach the Risk Kernel (fractional Kelly sizing, 2% per-trade cap, 35% sector cap) and get submitted as Alpaca paper orders.

The frontend verification panel shows the canonical JSON for any decision and recomputes the SHA-256 hash client-side. Judges can confirm it matches the on-chain record with no trusted intermediary. Later, outcome hashes are anchored against the same decision ID — building a tamper-proof reputation layer for the agent over time.

Contract: 0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887 on Mantle Mainnet.
Demo: https://sapa-fund.vercel.app
Repo: https://github.com/nikolas-sapa/sac-capital

Paper-only. LIVE_TRADING_ENABLED=false. On-chain records are verifiability anchors, not trading instructions.

### Project GitHub URL
https://github.com/nikolas-sapa/sac-capital

### Demo URL
https://sapa-fund.vercel.app

### Category
AI / Robotics

---

## TEAM INFORMATION SCREEN

### Member 1
- **Name:** Nikolas Sapalidis
- **Role:** Lead Developer
- **Contribution:** Architecture, AI pipeline, Mantle smart contract integration, frontend, investment strategy

### Member 2
- **Name:** Konstantopoulos Ilias
- **Role:** Contributor
- **Contribution:** Safety features and stock research

### Member 3
- **Name:** George Apostolakis
- **Role:** Contributor
- **Contribution:** Investment strategy and Mantle network funding
