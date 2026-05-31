# Crypto Up/Down Repricing Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development or executing-plans.
> **Status:** DRAFT — pending grill-me. **Depends on:** Foundation. **Build LAST.**

**Goal:** Trade short-duration BTC/ETH Up/Down markets by detecting the lag between the underlying spot price (Binance/Coinbase websocket) and Polymarket's repriced odds, plus binary-complete-set arbitrage when Up+Down < 1.0.

**Architecture:** Implements `core.Strategy` but is latency-sensitive — runs its own fast loop on two websocket feeds (spot price + CLOB book) rather than the slow periodic scan. Computes a fair Up probability from spot move + time-to-resolution, compares to market, signals when the gap exceeds costs. This is the most competitive lane; realistic expectation in paper mode is to learn whether we're fast enough at all.

**Tech Stack:** Foundation CLOB client, `websockets` for Binance/Coinbase spot, a simple fair-value model.

> **Reality check baked into this plan:** the documented edge here is *speed* (sub-100ms). In Python, on a home connection, against pro market-makers, we likely are NOT fast enough for pure repricing. So this plan front-loads a **latency measurement task** that can kill the directional-repricing approach early and fall back to the lower-bar **complete-set arbitrage** (which is about correctness, not raw speed).

---

### Task 1: Spot price websocket (TDD with fixture)

**Files:**
- Create: `strategies/crypto_updown/spot.py`, `tests/crypto/test_spot.py`, `tests/crypto/fixtures/binance_trade.json`

- [ ] **Step 1: Failing test** — `parse_trade(msg)` extracts price + timestamp from a Binance trade-stream message.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `SpotFeed.stream(symbol)` (Binance `wss://stream.binance.com`) + `parse_trade`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(crypto): binance spot price feed`.

---

### Task 2: LATENCY GATE — measure before building (manual + script)

**Files:**
- Create: `strategies/crypto_updown/latency_probe.py`

- [ ] **Step 1:** Script that subscribes to BOTH the spot feed and the Polymarket CLOB book for an active BTC Up/Down market, and logs: timestamp of each spot tick, timestamp of each CLOB reprice, and the measured delay between a significant spot move and the corresponding CLOB book change.
- [ ] **Step 2: DECISION GATE (manual)** — run for ≥1 hour during active trading. If the CLOB reprices faster than our loop can react (i.e., book already moved by the time we observe the spot move), pure directional repricing is dead for us → skip Tasks 4–5, go to arbitrage-only (Task 6). Document the measured numbers in the plan.
- [ ] **Step 3:** Commit `feat(crypto): latency probe + go/no-go data`.

---

### Task 3: Fair-value model (TDD)

**Files:**
- Create: `strategies/crypto_updown/fair_value.py`, `tests/crypto/test_fair_value.py`

- [ ] **Step 1: Failing test** — `fair_up_prob(spot_now, strike, seconds_left, vol)` returns 0.5 at-the-money with time left; →1.0 when far above strike near expiry; →0.0 when far below. (Simple lognormal/normal approximation.)
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement fair-value (normal-approx on log-returns with realized vol).
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(crypto): up/down fair-value model`.

---

### Task 4: Directional repricing signal (TDD) — ONLY IF latency gate passed

**Files:**
- Create: `strategies/crypto_updown/repricing.py`, `tests/crypto/test_repricing.py`

- [ ] **Step 1: Failing test** — given fair_up=0.65 and market ask(Up)=0.55, edge clears threshold → Signal on Up; within threshold → nothing. Bayesian shock override: on >8%/60s spot move, force re-evaluation.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement using `core.probability.bayes.is_shock` + fair-value vs. book.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(crypto): directional repricing signal`.

---

### Task 5: Fast loop runner (manual integration) — ONLY IF latency gate passed

**Files:**
- Create: `strategies/crypto_updown/fast_loop.py`

- [ ] **Step 1:** Implement a dedicated async loop consuming both feeds, emitting Signals to the paper executor in near-real-time (not the slow periodic scan).
- [ ] **Step 2: Manual** — paper-run during active markets; record fill quality.
- [ ] **Step 3:** Commit `feat(crypto): fast dual-feed loop`.

---

### Task 6: Complete-set arbitrage (TDD) — the lower-bar fallback

**Files:**
- Create: `strategies/crypto_updown/arbitrage.py`, `tests/crypto/test_arbitrage.py`

- [ ] **Step 1: Failing test** — `find_arb(book_up, book_down, fee)` returns a paired buy when `ask_up + ask_down + fees < 1.0`; sizes both legs equally; returns None otherwise.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement complete-set arb detector (buy both sides < $1, guaranteed $1 payout). Emit paired Signals.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(crypto): complete-set binary arbitrage`.

---

### Task 7: Strategy assembly + runner registration (TDD)

**Files:**
- Create: `strategies/crypto_updown/strategy.py`, `tests/crypto/test_strategy.py`

- [ ] **Step 1: Failing test** — strategy dispatches to repricing (if enabled) and/or arbitrage; respects Kelly/exposure caps via runner.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement + register `--strategy crypto`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5: Manual** paper-run.
- [ ] **Step 6:** Commit `feat(crypto): strategy assembly + runner`.

---

## Self-Review Checklist
- [ ] Latency gate (Task 2) runs BEFORE committing to directional repricing.
- [ ] Arbitrage fallback exists regardless of latency outcome.
- [ ] Fee/slippage included in arb math (a 1% gross edge can be net-negative).
- [ ] Fast loop does not block the other strategies' periodic scan.
