# Self-Improvement Harness + Obsidian Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development or executing-plans.
> **Status:** FINALIZED after grill. **Depends on:** Foundation (ledger + resolution loop) + ≥1 strategy producing resolved paper trades.

**Goal:** A bounded, evidence-gated learning loop that improves strategy performance over time by correcting calibration, learning systematic biases, re-tuning thresholds via walk-forward validation, and re-weighting capital — plus an Obsidian-based human-readable audit trail and approval inbox.

**Architecture:** A nightly consolidation job reads resolved trades from the ledger, runs each learning mechanism, and produces *proposed* parameter changes. Bounded calibration/bias corrections that pass walk-forward validation auto-apply; structural changes wait for human approval via Telegram + an Obsidian proposals inbox. Every change is versioned with a rollback guard that auto-reverts on measured degradation. All activity is journaled to the Obsidian vault.

**Tech Stack:** Foundation core, `scikit-learn` (isotonic/Platt calibration), `pandas`, plain markdown writes to the vault.

## Grill-Resolved Decisions
- **Autonomy:** bounded auto-apply for small validated corrections; **approval-gated** for structural changes (threshold moves beyond cap, disabling a strategy, anything code-level).
- **Learning scope:** all four — LLM calibration correction, per-station weather bias, walk-forward threshold re-tuning, capital re-weighting (feeds Plan 05's allocator).
- **Hard guardrails:** min-sample gates (no learning on tiny N), capped per-cycle step size, walk-forward validation required, version history + auto-rollback on degradation.

## Anti-Overfitting Principles (enforced in every task)
1. **No change without held-out evidence.** Every adjustment is validated on walk-forward out-of-sample resolved data, never in-sample.
2. **Minimum sample gates.** A category/station needs ≥N resolved trades before any correction is learned.
3. **Bounded steps.** No parameter moves more than a configured fraction per cycle. Prevents chasing noise.
4. **Versioned + reversible.** Every applied change snapshots the prior params; rollback guard reverts if the next window underperforms the pre-change baseline.
5. **Human gate for structural change.** Disabling strategies, large threshold jumps, or code changes always require approval.

## Obsidian Vault Layout (`/Users/nikolassapalidis/MyVault/02-Projects/polymarket-bot/`)
```
polymarket-bot/
├── index.md                 # live status: per-strategy ROI, bankroll, open positions
├── daily/YYYY-MM-DD.md       # nightly consolidation log (trades, learnings, changes)
├── strategies/<name>.md      # rolling performance + applied corrections per strategy
├── proposals/                # pending structural changes awaiting your approval
│   └── YYYY-MM-DD-<slug>.md  # one file per proposal: evidence, before/after, [ ] approve
└── params/CHANGELOG.md       # append-only history of every applied parameter change
```

---

### Task 1: Obsidian writer (TDD)

**Files:**
- Create: `harness/obsidian.py`, `tests/harness/test_obsidian.py`

- [ ] **Step 1: Failing test** — `ObsidianVault(root).write_daily(date, content)` writes to `daily/YYYY-MM-DD.md`; `append_changelog(entry)` appends to `params/CHANGELOG.md`; `write_proposal(slug, body)` creates a proposal file with an unchecked `- [ ] Approved` line; `update_index(stats)` rewrites `index.md`. Use a temp dir as the vault root in tests.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `ObsidianVault` (plain markdown file writes, idempotent index/section updates).
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(harness): obsidian vault writer`.

> Build this alongside Foundation if convenient — daily journaling is useful before any learning exists.

---

### Task 2: Versioned parameter store + rollback guard (TDD)

**Files:**
- Create: `harness/params.py`, `tests/harness/test_params.py`

- [ ] **Step 1: Failing test** — `ParamStore(path).get(strategy, key)` / `.set(strategy, key, value, reason, evidence)` snapshots the prior value with a version + timestamp; `.history(strategy, key)` lists versions; `.rollback(strategy, key)` restores the previous version. A `RollbackGuard(store, ledger)` reverts the most recent change to a key if the post-change resolved-trade window underperforms the pre-change baseline by more than a threshold.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `ParamStore` (sqlite/json with version rows) + `RollbackGuard`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(harness): versioned param store with rollback guard`.

---

### Task 3: LLM calibration learner (TDD)

**Files:**
- Create: `harness/learn/calibration.py`, `tests/harness/test_calibration.py`

- [ ] **Step 1: Failing test** — given resolved LLM trades (predicted_prob, outcome) per category, `fit_calibrator(samples, min_n=50)` returns an isotonic/Platt corrector ONLY when n≥min_n, else `None`. `apply(raw_prob)` maps a raw Claude prob to a corrected prob. Verify a deliberately over-confident input set gets pulled toward calibration.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement isotonic calibration with the min-sample gate.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(harness): llm calibration learner`.

---

### Task 4: Per-station weather bias learner (TDD)

**Files:**
- Create: `harness/learn/weather_bias.py`, `tests/harness/test_weather_bias.py`

- [ ] **Step 1: Failing test** — given resolved weather trades with (forecast_temp, actual_temp) per station, `learn_bias(samples, min_n=20, max_step=0.5)` returns a bounded per-station correction (e.g. Hong Kong +1.0°C) capped by `max_step` per cycle; returns 0.0 below min_n. Verify a station that systematically ran cold gets a positive correction within the cap.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement bounded bias estimator. Output feeds `strategies/weather/forecast.py` via the param store.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(harness): per-station weather bias learner`.

---

### Task 5: Walk-forward threshold re-tuner (TDD)

**Files:**
- Create: `harness/learn/retune.py`, `tests/harness/test_retune.py`

- [ ] **Step 1: Failing test** — `retune(param_grid, resolved_trades, validate_fn, max_step)` does walk-forward: split resolved trades into sequential train/validate windows, pick the param value that maximized out-of-sample expectancy, but clamp the move to `max_step` from the current value. Verify it never selects a value validated only in-sample, and never jumps more than max_step.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement walk-forward re-tuner (reuse logic patterns from evan-kolberg/prediction-market-backtesting where applicable).
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(harness): walk-forward threshold retuner`.

---

### Task 6: Proposal + approval workflow (TDD)

**Files:**
- Create: `harness/approval.py`, `tests/harness/test_approval.py`

- [ ] **Step 1: Failing test** — `classify_change(key, old, new, caps)` returns `"auto"` for bounded calibration/bias within caps, `"approval"` for structural changes (strategy enable/disable, threshold move beyond cap). `auto` changes apply immediately via ParamStore; `approval` changes write an Obsidian proposal + Telegram ping and DO NOT apply. `apply_approved(vault)` scans the proposals folder for checked `- [x] Approved` files and applies them.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement classification + apply-on-approval (you check the box in Obsidian, harness applies on next run).
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(harness): proposal and approval workflow`.

---

### Task 7: Nightly consolidation job (TDD + manual)

**Files:**
- Create: `harness/nightly.py`, `tests/harness/test_nightly.py`
- Create: `deploy/com.polymarketbot.nightly.plist`

- [ ] **Step 1: Failing test** — `run_nightly(ledger, store, vault, learners)` orchestrates: resolve open positions → recompute per-strategy stats → run each learner → classify changes (auto vs approval) → apply autos → run rollback guard → write the daily Obsidian log + update index + changelog. With stub inputs, assert autos applied, approvals queued, log written.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `run_nightly`. Add a launchd plist scheduling it ~02:30 (after the resolution poller at ~02:00).
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5: Manual** — run once against real paper data; confirm `daily/`, `index.md`, `params/CHANGELOG.md`, and any `proposals/` files appear in the vault, and a Telegram summary fires.
- [ ] **Step 6:** Commit `feat(harness): nightly self-improvement consolidation`.

---

### Task 8: Wire learned params back into strategies (TDD)

**Files:**
- Modify: `strategies/llm_probability/strategy.py` (apply calibrator), `strategies/weather/forecast.py` (apply station bias), each strategy's threshold reads
- Create: `tests/harness/test_integration.py`

- [ ] **Step 1: Failing test** — a strategy reads its live params from `ParamStore` at scan time; a learned calibration correction measurably changes its emitted `fair_prob`; a learned weather bias shifts the consensus center.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement param-store reads in each strategy (default to baseline when no learned value exists).
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(harness): strategies consume learned parameters`.

---

## Self-Review Checklist
- [ ] No learning mechanism applies without walk-forward / held-out validation.
- [ ] Min-sample gates prevent learning on noise.
- [ ] Every change is bounded, versioned, and auto-reverts on degradation.
- [ ] Structural changes require human approval via Obsidian checkbox + Telegram.
- [ ] Obsidian vault gets daily log, index, changelog, and proposal inbox.
- [ ] Strategies read live params at scan time (Task 8) — learning actually reaches the trades.
