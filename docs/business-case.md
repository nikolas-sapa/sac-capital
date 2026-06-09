# Business Case — Mantle-Verifiable AI Trading Agent

## The Problem

AI trading agents are opaque. An operator can claim any PnL, win rate, or strategy — and there is no way to verify it. Institutional capital cannot flow into AI-managed strategies without auditable track records. Current alternatives (CopyTrading, managed accounts, strategy vaults) all rely on centralized trust: you trust the operator's database, not the chain.

The result: AI alpha is locked out of serious capital allocation. The agents that exist either operate on retail-grade trust, or not at all.

---

## The Solution

An on-chain reputation layer for AI trading agents.

Every decision is committed to the chain — as a deterministic `bytes32` hash of the full structured payload — **before** the trade is placed. When the market resolves, the outcome hash is anchored against the original decision ID. The link between prediction and outcome is immutable and public.

Over time, agents accumulate track records that are not claimed by operators but anchored by the protocol. Anyone can audit them: recompute the hash, match it to the chain event, verify the outcome. No intermediary. No trust assumption.

---

## Market Opportunity

| Segment | Size / Signal |
|---|---|
| AI trading tools market | $4B+ (2025), growing ~30% YoY |
| Mantle ecosystem assets | $4B+ community-owned assets |
| Prediction markets (Polymarket) | $1B+ monthly volume |

**Target users:**

- **DeFi protocols** — need trusted, verifiable agent execution for vaults and yield strategies
- **Institutional investors** — require auditable AI track records before allocating capital
- **Retail traders** — want to mirror agents with proven on-chain history, not claimed performance
- **Fund managers** — need a compliant, portable track record that doesn't live in a proprietary database

---

## Business Model

Three viable paths, each independently fundable:

### 1. Protocol Fee
0.1% fee on trades executed by registered agents. Revenue scales directly with AUM under verified agents. At $100M AUM: $100K/year floor. At $1B: $1M/year. No users need to pay separately — the fee is embedded in execution.

### 2. Reputation SaaS
Subscription for fund managers and agent operators to mint and maintain agent identity (ERC-8004) plus a reputation NFT — a portable, on-chain credential that travels with the agent across protocols. Pricing: $200–500/month per agent. Target: 500 agents in Y1 = $1.2M–3M ARR.

### 3. Data Marketplace
Verified agent performance data (Brier scores, strategy win rates, drawdown profiles, sector allocation history) sold to quant funds, VC scouts, and protocol risk managers. The data has a property no other dataset has: it cannot be retroactively altered. Target buyers: risk desks, index providers, DeFi protocol governance committees.

---

## Post-Hackathon Roadmap

| Phase | Timeline | Milestones |
|---|---|---|
| **v1.0** | 3 months | Mainnet deploy, ERC-8004 identity live, outcome anchoring active, 500+ verified decisions across multiple agents |
| **v1.5** | 6 months | Agent marketplace — browse and filter agents by on-chain track record, connect wallet to mirror allocations |
| **v2.0** | 12 months | Protocol token — stake to vouch for agents, earn from protocol fee revenue; governance over registry parameters |

---

## Why Mantle

**Low gas** is the foundational requirement. Per-decision anchoring only works if anchoring every decision is economically viable — not just summary checkpoints. Mantle's gas costs make this possible. On Ethereum mainnet, the same architecture would price out 99% of use cases.

**Ecosystem alignment:**
- mETH and USDY are native assets the agent already trades and reports on — Mantle is not bolted on, it is the regime signal layer
- Mantle's institutional distribution channel is exactly where verified AI agents need to land to reach TradFi allocators
- The Mantle community treasury ($4B+) is potential early capital that benefits directly from a verifiable agent infrastructure it can audit

**Moat:** The registry is permissionless and chain-agnostic in design, but Mantle's economics and ecosystem make it the right home. First-mover in verifiable agent track records on Mantle creates compounding network effects — more anchored decisions → richer data → more capital → more agents registering.
