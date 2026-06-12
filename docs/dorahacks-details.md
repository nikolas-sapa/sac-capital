## Overview

SAC Capital is a multi-stage AI trading agent that makes every decision cryptographically verifiable on Mantle. Instead of trusting a dashboard, anyone can independently prove what the agent decided and why — before the outcome was known.

## The Problem

AI trading agents are black boxes. They publish returns but not reasoning. Theses get rewritten after the fact, win rates get cherry-picked, and there is no protocol-level mechanism for an agent to prove it made a decision *before* the outcome resolved.

## How It Works

**Stage 1 — Screening**
The agent runs a deterministic equity screen on US markets: event catalysts (earnings, 8-K filings), relative strength, quality, and inflection signals. Only candidates that pass all screens reach the LLM.

**Stage 2 — LLM Pipeline**
Each candidate passes through five stages:
1. Haiku pre-filter — fast rejection of weak setups
2. Sonnet bull analyst — full thesis with entry, stop-loss, take-profit, catalyst
3. Sonnet challenger — steelmans the bear case
4. Auditor — arbitrates bull vs. challenger and produces final verdict
5. Risk Kernel — fractional Kelly sizing, 2% per-trade cap, 35% sector cap

**Stage 3 — Commitment**
Before any order is placed, the full decision payload (strategy, confidence, thesis, risk parameters) is serialized to canonical JSON and hashed to `bytes32` via SHA-256. This hash is submitted to `AgentDecisionRegistry` on Mantle Mainnet.

**Stage 4 — Execution**
Approved decisions are submitted as paper orders via Alpaca. The local ledger records fills, partial fills, and rejections.

**Stage 5 — Verification**
The frontend verification panel shows the canonical JSON for any decision and recomputes the hash client-side. Judges can confirm it matches the on-chain record — zero trust required.

## On-Chain

- **Contract:** `AgentDecisionRegistry.sol` on Mantle Mainnet
- **Address:** `0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887`
- **Deploy tx:** `0x46bbaa02a9e7fd1025f00896c70405978cc3596e04d0559e07c5c1b0cac1222b`
- **Function:** `recordDecision(bytes32 agentId, bytes32 decisionHash, string uri)`
- **Outcome anchoring:** `recordOutcome` links verified results back to the same decision ID — building a tamper-proof reputation layer over time

## Safety

Paper-only. `LIVE_TRADING_ENABLED=false`. Alpaca paper URLs enforced at the executor level. On-chain hashes are verifiability anchors — not custody or trading instructions.

## Demo

[sapa-fund.vercel.app](https://sapa-fund.vercel.app) — live decisions, real Alpaca portfolio history chart, and hash verification panel.
