# Orchestrator (Capital Allocator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development or executing-plans.
> **Status:** DRAFT — pending grill-me. **Depends on:** Foundation + ≥2 strategies live in paper.

**Goal:** A "boss" layer that sits above the strategies, allocates the shared bankroll across them based on demonstrated performance and confidence, enforces portfolio-level risk, and resolves conflicts when strategies want the same market.

**Architecture:** The orchestrator does NOT generate signals. It collects signals from all enabled strategies each cycle, deduplicates/reconciles overlapping markets, allocates capital per strategy via performance-weighted budgets, applies portfolio risk caps, and hands final sized orders to the executor. It reads each strategy's rolling track record from the ledger.

**Tech Stack:** Foundation core (ledger, kelly, executor), `pandas` for rolling-performance stats.

> **Sequencing note:** Do NOT build this until LLM + Weather bots both run in paper mode. Premature orchestration optimizes a system with nothing to allocate.

---

### Task 1: Strategy performance tracker (TDD)

**Files:**
- Create: `orchestrator/performance.py`, `tests/orch/test_performance.py`

- [ ] **Step 1: Failing test** — `StrategyStats(ledger).rolling(strategy_name, window=30)` returns ROI, win rate, Brier (where applicable), realized Sharpe-like score over last N resolved trades.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement rolling per-strategy stats from the ledger.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(orch): rolling strategy performance tracker`.

---

### Task 2: Capital allocator (TDD)

**Files:**
- Create: `orchestrator/allocator.py`, `tests/orch/test_allocator.py`

- [ ] **Step 1: Failing test** — `allocate(bankroll, stats)` splits bankroll into per-strategy budgets proportional to a score (e.g. positive-expectancy strategies get more), with a floor (every enabled strategy gets a minimum exploration budget) and a ceiling (no strategy > max_share). New strategies with no track record get the exploration floor.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement performance-weighted allocation with floor/ceiling.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(orch): performance-weighted capital allocator`.

---

### Task 3: Conflict reconciliation (TDD)

**Files:**
- Create: `orchestrator/reconcile.py`, `tests/orch/test_reconcile.py`

- [ ] **Step 1: Failing test** — given two signals on the same `condition_id`+`token_id`, keep the higher-confidence one and merge stake intent (don't double-bet). Given opposing signals (one buys Yes, another buys No on same market), net them / flag and skip.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `reconcile(signals)`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(orch): signal conflict reconciliation`.

---

### Task 4: Portfolio risk gate (TDD)

**Files:**
- Create: `orchestrator/risk.py`, `tests/orch/test_risk.py`

- [ ] **Step 1: Failing test** — `RiskGate` enforces: total open exposure ≤ `max_total_exposure_pct * bankroll`; per-strategy daily loss limit halts that strategy; single position ≤ 2% bankroll. Returns the trimmed/approved order set.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement risk gate reading open positions + today's PnL from ledger.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(orch): portfolio risk gate`.

---

### Task 5: Orchestrated runner (TDD + manual)

**Files:**
- Modify: `runner.py`
- Create: `tests/orch/test_orchestrated_runner.py`

- [ ] **Step 1: Failing test** — with two stub strategies and a fake ledger, the orchestrated cycle: collect signals → reconcile → allocate budgets → size via Kelly within budget → risk gate → paper-execute. Assert caps respected and budgets honored.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `--mode orchestrated` in `runner.py` chaining performance → allocate → reconcile → size → risk → execute.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5: Manual** — run orchestrated paper mode with LLM + Weather enabled; Telegram reports per-strategy allocation + fills.
- [ ] **Step 6:** Commit `feat(orch): orchestrated multi-strategy runner`.

---

### Task 6: Daily report (TDD)

**Files:**
- Create: `orchestrator/report.py`, `tests/orch/test_report.py`

- [ ] **Step 1: Failing test** — `daily_report(ledger)` produces per-strategy ROI/win-rate/exposure + portfolio totals as a formatted message.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement; schedule via a nightly cron to Telegram.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(orch): nightly portfolio report`.

---

## Self-Review Checklist
- [ ] Orchestrator generates NO signals — pure allocation/risk/reconciliation.
- [ ] New strategies get an exploration floor, not zero.
- [ ] Portfolio exposure cap + per-strategy daily loss limit enforced.
- [ ] Conflict logic prevents double-betting and opposing self-trades.
