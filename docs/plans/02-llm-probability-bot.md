# LLM Probability Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development or executing-plans.
> **Status:** DRAFT — pending grill-me. **Depends on:** Foundation.

**Goal:** A strategy that reads a Polymarket question + current price, asks Claude for a calibrated true probability, and signals when the model's edge vs. market price clears a threshold.

**Architecture:** Implements `core.Strategy`. For each candidate market, build a prompt (question + resolution rules + current YES/NO prices), call Claude, parse a structured probability + confidence, compute edge, emit `Signal` only when edge and calibration gates pass. The 87%-of-edge claim from the research lives in this one call — so calibration discipline matters more than cleverness.

**Tech Stack:** Foundation core, `anthropic` SDK (direct) OR Vercel AI Gateway `"anthropic/claude-..."` string, `pydantic` for structured output parsing.

---

> **Edge thesis (from grill):** trade THIN/ILLIQUID markets where sharp money is absent. The filter must bias toward low-volume, mispriced markets — not the liquid headline markets where the crowd is already efficient.
> **Cost control (from grill):** two-stage. A cheap Haiku pass scores the candidate set first; Sonnet runs the calibrated estimate only on survivors. A daily USD budget guard halts LLM calls when exceeded.

### Task 1: Market filter (TDD)

**Files:**
- Create: `strategies/llm_probability/filters.py`, `tests/llm/test_filters.py`

- [ ] **Step 1: Failing test** — `is_candidate(market)` rejects: already-resolved, <X hours to resolution, illiquid-in-the-bad-way (no bid/ask at all), or both prices in [0.05, 0.95] dead zone configurable. ACCEPTS low-volume markets (low volume is the edge, not a disqualifier) that still have a tradeable book. Add `liquidity_score(market)` to rank thin-but-tradeable markets.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `is_candidate` + `candidate_markets(markets)`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(llm): market candidate filter`.

---

### Task 2: Prompt builder (TDD)

**Files:**
- Create: `strategies/llm_probability/prompt.py`, `tests/llm/test_prompt.py`

- [ ] **Step 1: Failing test** — `build_prompt(market, resolution_text)` includes the question, resolution criteria, current YES/ask, and an explicit instruction to return JSON `{"probability": float, "confidence": float, "reasoning": str}`; forbids hedging.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `build_prompt`. System prompt enforces calibration ("you will be scored by Brier score; do not anchor to 0.5").
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(llm): calibrated probability prompt builder`.

---

### Task 3: Two-stage LLM client + budget guard (TDD with mock)

**Files:**
- Create: `strategies/llm_probability/llm.py`, `strategies/llm_probability/budget.py`, `tests/llm/test_llm.py`, `tests/llm/test_budget.py`

- [ ] **Step 1: Failing test (budget)** — `DailyBudget(limit_usd).allow(est_cost)` returns True until cumulative spend would exceed `limit_usd`, then False; resets daily.
- [ ] **Step 2:** Run, fail. Implement `DailyBudget`. Run, pass.
- [ ] **Step 3: Failing test (llm)** — `prefilter(markets)` (Haiku) returns a cheaply-scored shortlist; `estimate_probability(prompt)` (Sonnet) parses a mocked JSON response into `ProbEstimate(probability, confidence, reasoning)`; rejects out-of-range probs; retries once on malformed JSON; refuses to call when budget guard denies.
- [ ] **Step 4:** Run, fail.
- [ ] **Step 5:** Implement two-stage client (mockable injection, no real API in tests) wired to `DailyBudget`.
- [ ] **Step 6:** Run, pass.
- [ ] **Step 7:** Commit `feat(llm): two-stage estimator with daily budget guard`.

---

### Task 4: Strategy assembly (TDD)

**Files:**
- Create: `strategies/llm_probability/strategy.py`, `tests/llm/test_strategy.py`

- [ ] **Step 1: Failing test** — `LLMProbabilityStrategy(client).scan([market])`: with injected estimate p=0.7 and ask=0.5, emits a `Signal` (edge=0.2, confidence passed through); with p=0.52 ask=0.5 (below `min_edge`), emits nothing.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement: filter → prompt → estimate → `edge = p - ask`; emit `Signal(fair_prob=p, price=ask, confidence=...)` when `edge >= min_edge` AND `confidence >= min_conf`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(llm): probability strategy`.

---

### Task 5: Calibration harness (TDD)

**Files:**
- Create: `strategies/llm_probability/calibration.py`, `tests/llm/test_calibration.py`

- [ ] **Step 1: Failing test** — given a list of (predicted_prob, actual_outcome), `brier_score()` and `calibration_buckets()` compute correctly.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement Brier + bucketed calibration plot data. This is how we validate the LLM is actually calibrated before trusting it with capital.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(llm): calibration scoring`.

---

### Task 6: Dry-run validation against resolved markets

**Files:**
- Create: `strategies/llm_probability/backtest.py`

- [ ] **Step 1:** Script: pull N already-resolved markets from gamma-api (with known outcomes), run the LLM estimate on each as if pre-resolution, score Brier + simulated PnL with Kelly sizing.
- [ ] **Step 2: Manual gate** — run on ≥50 resolved markets. Record Brier score and simulated ROI. If Brier > 0.25 (worse than random-ish) the LLM has no edge here → STOP, do not paper-trade live.
- [ ] **Step 3:** Commit `feat(llm): resolved-market backtest harness`.

---

### Task 7: Wire into runner

- [ ] **Step 1:** Register `LLMProbabilityStrategy` as `--strategy llm` in `runner.py`.
- [ ] **Step 2: Manual** — run one paper loop; confirm signals → Kelly-sized paper fills → ledger → Telegram.
- [ ] **Step 3:** Commit `feat(llm): register strategy in runner`.

---

## Self-Review Checklist
- [ ] Calibration is validated on resolved markets BEFORE paper trading (Task 6 gate).
- [ ] No raw-prob trust without Brier check.
- [ ] LLM cost bounded (filter cuts candidate set before any API call).
