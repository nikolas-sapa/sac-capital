# SAC Capital

**Track:** AI Alpha & Data
**Demo:** https://sapa-fund.vercel.app
**Contract (Mantle Mainnet):** `0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887`
**Deploy tx:** `0x46bbaa02a9e7fd1025f00896c70405978cc3596e04d0559e07c5c1b0cac1222b`
**Explorer:** https://explorer.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887

---

## 1. The Problem

AI trading agents are black boxes. PnL numbers, win rates, and strategy claims are all unauditable. Fund managers, DeFi protocols, and retail users cannot trust an agent they cannot inspect — and there is currently no protocol-level mechanism for an agent to prove it made a decision *before* the outcome was known.

---

## 2. Our Solution

Before execution, the agent serializes its full decision (strategy, confidence, thesis, risk parameters) into canonical JSON. That JSON is deterministically hashed to `bytes32` and anchored in `AgentDecisionRegistry` on Mantle — **before the trade is placed**.

Later, when the outcome resolves, a matching outcome hash is recorded against the same decision ID. Anyone can recompute the hash from the public payload and confirm it matches the Mantle record — no trusted intermediary required.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│                  AI Agent Pipeline                   │
│  Event Screen → Haiku Filter → Sonnet Bull Thesis   │
│  → Sonnet Challenger → Auditor → Risk Kernel         │
└────────────────────────┬────────────────────────────┘
                         │ structured decision JSON
                         ▼
┌─────────────────────────────────────────────────────┐
│            Commitment Exporter                       │
│  canonical JSON → sha256 → bytes32                  │
└────────────────────────┬────────────────────────────┘
                         │ bytes32 hash
                         ▼
┌─────────────────────────────────────────────────────┐
│         AgentDecisionRegistry.sol (Mantle)          │
│  recordDecision(agentId, bytes32, uri) → event      │
└────────────────────────┬────────────────────────────┘
                         │ on-chain commitment
                         ▼
┌─────────────────────────────────────────────────────┐
│           Verifier Frontend (Vercel)                 │
│  payload + recomputed hash vs on-chain record       │
│  Anyone can verify: hash(payload) == Mantle event   │
└─────────────────────────────────────────────────────┘
```

---

## 4. How to Verify (step by step)

1. Visit https://sapa-fund.vercel.app
2. Pick any decision card and note the `bytes32` hash shown
3. Copy the JSON payload shown in the Verify panel
4. Compute SHA-256 of the canonical JSON (sorted keys, no spaces) — it should match the `bytes32`
5. Search the contract on Mantle Explorer via the address above — find the matching `DecisionRecorded` event
6. The on-chain hash = the recomputed hash = the displayed hash → verifiably anchored before execution

**Manual hash check (Python):**

```python
import json, hashlib
payload = { ... }  # paste from the Verify panel
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
print("0x" + hashlib.sha256(canonical.encode()).hexdigest())
# must equal the bytes32 shown on the card and in the Mantle event
```

---

## 5. Strategy & Risk Management

**LLM pipeline (multi-stage):**
- Haiku prefilter — fast, cheap rejection of low-quality candidates
- Sonnet bull thesis — full structured analysis with evidence citations
- Sonnet challenger — must identify a specific weakness in the bull case
- Auditor sign-off — final gate before risk kernel

**Risk kernel:**
- Fractional Kelly 0.5 sizing
- Per-trade cap: 2% of bankroll
- Per-name cap: 25% of portfolio
- Sector cap: 35% of portfolio

**Integrity guards:**
- NaN guards at Pydantic schema level + `math.isfinite` check in kernel — invalid decisions are rejected before anchoring
- Invalid LLM output (malformed JSON, missing fields, `entry <= 0`, `stop_loss >= entry`, confidence outside `[0,1]`) is rejected before a `Recommendation` is created
- 485 tests, including integration tests for the commitment hashing pipeline

**Safety boundary:** paper-only — no live capital at risk during the hackathon.

---

## 6. Mantle Integration

**`AgentDecisionRegistry.sol`** is minimal and gas-efficient: no oracle, no custody, no execution logic. It is a pure commitment layer.

| Function | Purpose |
|---|---|
| `recordDecision(agentId, bytes32, uri)` | Anchor decision hash before trade |
| `recordOutcome(id, bytes32, uri)` | Link resolved outcome hash to decision ID |
| `decision(id)` | Public read of any decision record |
| `outcome(id)` | Public read of resolved outcome |

**On-chain signals used by the agent:**
- mETH APY — macro regime context (risk-on/risk-off signal)
- Mantle gas price — used as execution cost input in sizing decisions

**ERC-8004 agent identity:** [pending registration with competition infrastructure]

**Why every decision is anchored (not just summaries):** Mantle's low gas makes per-decision anchoring economically viable. This is the property that makes the track record genuinely immutable rather than selectively curated.

---

## 7. Reproduce Locally

```bash
git clone https://github.com/nikolas-sapa/sac-capital
uv sync

# Export decision commitments from the paper ledger
python scripts/export_mantle_commitments.py --out data/out.jsonl

# Dry-run submission (no tx sent)
python scripts/submit_mantle_decisions.py \
  --commitments data/out.jsonl \
  --contract 0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887 \
  --agent-id mantle-verifiable-ai-agent \
  --dry-run --limit 3

# Run tests
python -m pytest
```

**Deploy the contract yourself (Foundry):**

```bash
export MANTLE_RPC_URL=https://rpc.sepolia.mantle.xyz
export MANTLE_PRIVATE_KEY=0x...

forge test
forge script contracts/script/DeployAgentDecisionRegistry.s.sol \
  --rpc-url "$MANTLE_RPC_URL" \
  --broadcast
```

---

## 8. Self-Improvement Loop

The agent runs a nightly self-improvement harness: it reads its own performance data (Brier scores, win rates by strategy) and proposes prompt edits — but only promotes changes that pass an evidence gate (improvement must be statistically significant, not noise).

This loop is bounded and auditable: proposed changes are logged as research artifacts that are themselves anchored on Mantle. The agent cannot silently rewrite its own strategy; every proposed change leaves an immutable trail.

---

## 9. Team

| Name | Role |
|---|---|
| **Nikolas Sapalidis** | Lead Developer — architecture, Mantle integration, AI pipeline, frontend, investment strategy |
| **Konstantopoulos Ilias** | Safety features & stock research |
| **George Apostolakis** | Investment strategy & Mantle network funding |

**Site:** [nikolas.helpmarq.com](https://nikolas.helpmarq.com)
