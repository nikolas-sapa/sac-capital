# polymarket-bot

An autonomous paper-trading research system for [Polymarket](https://polymarket.com) prediction markets and US equities. All LLM analysis routes through your **Claude subscription** via `claude -p` — no Anthropic API key required.

---

## Architecture

```
runner.py                   ← Polymarket orchestrated runner
runner_equities.py          ← US equities paper runner

strategies/
  llm_probability/          ← Plan 02 — Haiku prefilter → Sonnet edge estimate
  weather/                  ← Plan 03 — NWS forecast vs. market consensus
  crypto_updown/            ← Plan 04 — BTC spot/CLOB arb + repricing

orchestrator/               ← Plan 05 — multi-strategy capital allocation + risk gate
harness/                    ← Plan 06 — nightly self-improvement (calibration, retuning, Obsidian vault)

equities/
  screen/                   ← Plan 07b — event screen (earnings, SEC filings) + quality screen
  analysis/                 ← Plan 07c — two-stage LLM analyst (Haiku → Sonnet)
  risk/                     ← Plan 07d — gap-adjusted sizing, exit signals, risk kernel
  killgate/                 ← Plan 07e — forward paper tracker + Revolut-cost kill-gate
  improve/                  ← Plan 07f — parameter tournament, auto-promoter

core/
  claude_client.py          ← ClaudeCodeClient — `claude -p` subprocess wrapper
  clob/                     ← Polymarket CLOB WebSocket + Gamma REST client
  ledger.py                 ← Trade ledger with PnL tracking (SQLite)
  execution/paper.py        ← Paper executor with slippage + fee model
```

---

## Plans

| # | Plan | Status |
|---|------|--------|
| 01 | Core infrastructure (CLOB, ledger, paper execution, Kelly sizing) | ✅ |
| 02 | LLM probability strategy (Haiku prefilter → Sonnet deep estimate) | ✅ |
| 03 | Weather strategy (NWS multi-model consensus vs. market) | ✅ |
| 04 | Crypto up/down (BTC spot feed, CLOB arb, latency probe) | ✅ |
| 05 | Orchestrator (performance-weighted allocation, reconcile, risk gate) | ✅ |
| 06 | Self-improvement harness (calibration, retuning, Obsidian vault, nightly) | ✅ |
| 07a | Equities domain types + foundation | ✅ |
| 07b | Event screener (earnings, 8-K filings) + quality screener | ✅ |
| 07c | Two-stage equity analyst (Haiku prefilter → Sonnet thesis) | ✅ |
| 07d | Equity risk kernel (gap-adjusted stop sizing, exit signals) | ✅ |
| 07e | Kill-gate + forward paper tracker (≥100 trades + positive net PnL gate) | ✅ |
| 07f | Auto-promoter + parameter tournament (OOS scoring, rollback guard) | ✅ |

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- [Claude Code CLI](https://claude.ai/code) — logged in with an active subscription
- ProtonVPN (or equivalent) active when running Polymarket strategies — Polymarket is geo-blocked in some regions

---

## Setup

```bash
git clone https://github.com/nikolas-sapa/polymarket-bot.git
cd polymarket-bot
uv sync
cp .env.example .env   # optional — no API key needed for Claude
```

No API key required. LLM calls use `claude -p` (your Claude subscription).

---

## Running

### Polymarket — all strategies, orchestrated

```bash
PYTHONPATH=. uv run python runner.py --strategy llm,weather,crypto_updown --mode orchestrated
```

### Polymarket — single strategy

```bash
PYTHONPATH=. uv run python runner.py --strategy weather --mode simple
```

### Equities paper runner

```bash
PYTHONPATH=. uv run python runner_equities.py           # screen + analyse
PYTHONPATH=. uv run python runner_equities.py --no-analyse   # screen only
PYTHONPATH=. uv run python runner_equities.py --mark-only    # mark-to-market
```

### Latency probe (BTC Up/Down markets)

```bash
# Get token IDs from browser console on polymarket.com:
# fetch('https://clob.polymarket.com/markets/<conditionId>').then(r=>r.json()).then(d=>d.tokens.forEach(t=>console.log(t.token_id,'|',t.outcome)))

PYTHONPATH=. uv run python strategies/crypto_updown/latency_probe.py \
  --market <conditionId> \
  --tokens "<yesTokenId>,<noTokenId>" \
  --duration 300
```

**Verdict:** median lag < 500ms → directional repricing viable; ≥ 500ms → arb-only mode.

### Tests

```bash
PYTHONPATH=. uv run pytest          # 429 tests
```

---

## LLM Routing

All LLM calls go through `claude -p` — your active Claude Code subscription, not an API key.

```
ClaudeCodeClient.complete()
  └─ subprocess: claude -p --model <model> <prompt>
       ├─ Haiku  — prefilter / cheap scoring passes
       └─ Sonnet — deep analysis (equity thesis, probability estimate)
```

`DailyBudget` is set to $999 (subscription billed monthly, not per-token) so it never blocks.

---

## Key Design Decisions

- **Paper-only until kill-gate clears** — no real capital until ≥100 forward-paper trades with positive net PnL after Revolut 0.25%/leg + 2% gap penalty
- **Geo-block handling** — CLOB REST API requires VPN in the terminal; token IDs can be obtained via browser console and passed with `--tokens`
- **Subscription LLM** — `claude -p` subprocess avoids API key dependency; 180s timeout with graceful per-market skipping on slow responses
- **Self-improvement** — nightly harness recalibrates probability estimates, rebalances strategy weights, and writes proposals to Obsidian vault for human approval

---

## Repository Structure

```
polymarket-bot/
├── core/               ← shared infra (CLOB, ledger, sizing, claude client)
├── strategies/         ← Polymarket strategies (llm, weather, crypto)
├── orchestrator/       ← multi-strategy runner (allocate, reconcile, risk)
├── harness/            ← nightly self-improvement (params, vault, learners)
├── equities/           ← equity swing/core trading pipeline
├── tests/              ← 429 unit tests (pytest)
├── docs/plans/         ← implementation plans (SPEC + 7 milestones)
├── scripts/            ← browser console helpers (find markets, token IDs)
├── runner.py           ← Polymarket CLI entry point
└── runner_equities.py  ← Equities CLI entry point
```

---

## License

MIT
