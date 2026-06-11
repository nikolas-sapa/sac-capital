# Mantle-Verifiable AI Trading Agent

> AI trading decisions are exported as deterministic `bytes32` commitments and anchored on Mantle — anyone can verify agent behavior and outcomes.

**Track:** AI Alpha & Data · Turing Test Hackathon 2026

| | |
|---|---|
| Demo | [sapa-fund.vercel.app](https://sapa-fund.vercel.app) |
| Contract | [`0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887`](https://explorer.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887) |
| Deploy tx | [`0x46bbaa...`](https://explorer.mantle.xyz/tx/0x46bbaa02a9e7fd1025f00896c70405978cc3596e04d0559e07c5c1b0cac1222b) |
| Decision tx | [`0x94ac57...`](https://explorer.mantle.xyz/tx/0x94ac5787a23f472a9d97e3ca435b9dc4818b734e0b3efad9ad2d2fd1251c6076) |

---

## How It Works

```
US Equity Event Screen
  → Haiku pre-filter
  → Sonnet bull thesis
  → Sonnet challenger
  → Auditor
  → Risk Kernel (fractional Kelly, 2% per-trade cap, 35% sector cap)
  → Alpaca paper order + local ledger entry
  → Deterministic canonical JSON exporter
  → AgentDecisionRegistry on Mantle (bytes32 SHA-256 commitment)
  → Frontend verification panel
```

Mantle is the immutable benchmark layer. The agent hashes each decision payload with canonical JSON → SHA-256 → `bytes32`, records it on-chain, and can later anchor outcome hashes against the same decision ID. The frontend recomputes the hash client-side so reviewers can confirm the on-chain record matches the AI output.

**Safety boundary:** paper-only. On-chain records are verifiability anchors — not custody, brokerage, or live-trading instructions.

---

## Reproduce Locally

**Dependencies**

```sh
uv sync
```

**Tests**

```sh
./.venv/bin/python -m pytest
```

**Export decision commitments**

```sh
./.venv/bin/python scripts/export_mantle_commitments.py \
  --ledger data/ledger.db \
  --out data/mantle_commitments.jsonl
```

**Dry-run Mantle submission**

```sh
./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract 0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887 \
  --agent-id mantle-verifiable-ai-agent \
  --limit 1
```

**Deploy contract** (Foundry required, funded Mantle wallet)

```sh
export MANTLE_RPC_URL=https://rpc.mantle.xyz
export MANTLE_PRIVATE_KEY=0x...

forge test
forge script contracts/script/DeployAgentDecisionRegistry.s.sol \
  --rpc-url "$MANTLE_RPC_URL" \
  --broadcast
```

**Frontend**

```sh
cd frontend
npm install
npm run dev
```

---

## Repository Layout

```
core/             Config, ledgers, alerts, LLM adapters
equities/
  analysis/       Equity analyst, typed LLM schemas, budget controls
  data/           Prices, fundamentals, calendar, filings, news, macro, VIX
  eval/           Research artifact replay and report
  execution/      Alpaca paper execution and reconciliation
  killgate/       Forward-paper tracker and promotion gates
  research/       Artifact store and offline research modules
  risk/           Sizing, exits, risk kernel
  screen/         Event, quality, inflection, thematic, relative-strength
contracts/        AgentDecisionRegistry.sol (Mantle)
scripts/          Commitment exporter, Mantle submission, nightly maintenance
frontend/         React/Vite verification dashboard
tests/            481-test regression suite
docs/             Operator runbooks
deploy/           macOS launchd plists
```

---

## Equities Pipeline

`runner_equities.py` runs the full loop:

1. Mark open positions and check exits
2. Classify macro regime
3. Check thesis health on open swing positions
4. Check thematic concentration
5. Run event screen (earnings + recent 8-K catalysts)
6. Add relative-strength, trend, base, breakout-volume evidence
7. Run quality and inflection screens
8. Apply VIX entry gate
9. Run LLM pre-filter → analyst → challenger → auditor
10. Validate with Pydantic; reject malformed outputs
11. Write research artifacts for all analysed candidates
12. Pass through risk kernel
13. Submit Alpaca paper orders or internal paper fills

---

## Key Configuration

```sh
EXECUTION_PROVIDER=internal_paper   # never alpaca_live
LIVE_TRADING_ENABLED=false
EQUITY_RISK_PCT=0.02
EQUITY_MAX_POSITIONS=4
EQUITY_MAX_SECTOR_PCT=0.35
EQUITY_DAILY_LOSS_LIMIT_PCT=0.05

# Alpaca paper
ALPACA_PAPER=true
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_API_KEY_ID=...
ALPACA_SECRET_KEY=...

# LLM
ANTHROPIC_FAST_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_STRONG_MODEL=claude-sonnet-4-6
```

---

## Team

| Name | Role |
|---|---|
| **Nikolas Sapalidis** | Lead Developer — architecture, Mantle integration, AI pipeline, frontend |
| Team | Assisted with trading principles |

[nikolas.helpmarq.com](https://nikolas.helpmarq.com)
