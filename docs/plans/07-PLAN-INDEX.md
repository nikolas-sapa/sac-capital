# Plan 07 — Equities Analyst Bot — Plan Index

Spec: `07-equities-analyst-SPEC.md`. Build order; each milestone is shippable + testable on its own and gets its **own** full TDD plan (like Plans 01–06) when its predecessor lands and its research items are resolved.

> **Stress-tested via `/grill-me` (2026-06-01).** Charters below reflect grill resolutions — see the SPEC's "Grill-Resolved Revisions".

| # | Milestone | Plan file | Status | Blocked on |
|---|---|---|---|---|
| 07a | **Equity Foundation** (prices feed only) | `07a-equity-foundation-PLAN.md` | **DETAILED — ready to build** | — |
| **07-SPIKE** | **Synthesis proof (throwaway)** | _to write (1-day, no tests)_ | **gate — build right after 07a** | 07a done |
| 07b | Screening — **events, not moves** | _to write_ | charter only | 07-SPIKE looks promising + event-screen definitions researched |
| 07c | Analyst engine (reject already-priced) | _to write_ | charter only | 07b + LLM prompt/budget design |
| 07d | Risk kernel (guardian process) + paper tracker | _to write_ | charter only | 07c + Revolut OCO/cost verification |
| 07e | Forward-paper instrumentation (KILL-GATE) | _to write_ | charter only | 07d |
| 07f | Self-improvement harness | _to write_ | charter only | 07e |
| — | Cross-venue orchestrator | _later plan_ | deferred | both funds have paper track records |

## Charters (scope only — NOT implementation plans)

### 07-SPIKE — Synthesis proof (throwaway, ~1 day, NO tests)
Hardcode ~10 catalyst tickers; pull real SEC filings + recent news; hand each bundle to Claude with the analyst prompt (thesis + entry/stop/take-profit + confidence); print 10 recommendations and eyeball them (specific & grounded in the docs, or generic vibes?). Optionally forward-paper-track 2–4 weeks. **Purpose: kill the project cheaply if Claude's synthesis is garbage, BEFORE building 07b+.** Deleted after; the clean version is 07c.

### 07b — Screening (events, not moves)
Build `equities/screen/event_screen.py` (small/mid-cap: **upcoming earnings dates, recent earnings *surprises* for post-earnings drift, fresh 8-Ks/filings** — NOT "already up X%") and `quality_screen.py` (large-cap quality for DCA core). Input: universe of `Instrument`. Output: ranked candidate `Instrument`s + the *event* that flagged them. **Research first:** concrete event-signal definitions, universe source.

### 07c — Analyst engine
Build `equities/analysis/analyst.py`: two-stage Claude pipeline (Haiku filter ranks → Sonnet writes thesis + entry/stop/take-profit on survivors), hard candidate cap + daily USD budget guard. **Claude's #1 rule: REJECT setups where the re-rating is already complete** (the "already moved = too late" insight). Output: `Recommendation`s. **Research first:** prompt design, cost model, budget-guard mechanics.

### 07d — Risk kernel (guardian process) + paper tracker
Build `equities/risk/kernel.py` as a **separate guardian process** (sealed fuses: gap-aware per-trade cap 1–2%, **max concurrent positions ~4**, **per-name concentration ≤25%**, max daily loss, max position size, total-drawdown breaker, real-money promotion gate, auto-rollback) — the strategy/rewriter cannot import or write to it. Plus `risk/sizing.py` (fractional shares from stop distance + cap), `risk/exits.py` (stop/target/time-stop), `equities/paper.py` (records to `EquityLedger`, nightly mark-to-market, fires exits). **Verify first:** Revolut OCO/bracket + exact commission.

### 07e — Forward-paper instrumentation (THE KILL-GATE)
Build forward-paper tracking with a **cost model = 0.25%/leg + FX + gap-aware stop fills**. **Gate = ≥100 real-time forward paper trades, positive expectancy net of costs** → only then real-capital-eligible. A disposable **price-only mechanical pre-filter** (survivorship caveat stamped) may kill broken params early but is NEVER the trust oracle. No survivorship-free historical backtest (free data can't supply it honestly).

### 07f — Self-improvement harness
Build `equities/improve/`: autonomous variant generation + tournament on forward-paper data, **auto-promotion to real capital gated by kill-gate pass + min live-paper track record + cooldown rate-limit (math, no human)**, auto-rollback on live degradation, Obsidian audit log. Bounded by the guardian-process risk kernel (per the spec's eyes-open full-autonomy override). **Research first:** variant representation, promotion/rollback thresholds, walk-forward split policy.

### (Later) Cross-venue orchestrator
Generalize Plan 05 into the single allocator ("hedge-fund boss") that splits one real-capital pool across the Polymarket strategies and the equity `Fund`. Built last — only sensible once each fund has a real paper track record.
