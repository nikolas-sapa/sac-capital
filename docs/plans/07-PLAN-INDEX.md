# Plan 07 — Equities Analyst Bot — Plan Index

Spec: `07-equities-analyst-SPEC.md`. Build order; each milestone is shippable + testable on its own and gets its **own** full TDD plan (like Plans 01–06) when its predecessor lands and its research items are resolved.

| # | Milestone | Plan file | Status | Blocked on |
|---|---|---|---|---|
| 07a | **Equity Foundation** | `07a-equity-foundation-PLAN.md` | **DETAILED — ready to build** | — |
| 07b | Screening | _to write_ | charter only | 07a done + swing-signal definitions researched |
| 07c | Analyst engine | _to write_ | charter only | 07b + LLM prompt/budget design |
| 07d | Risk kernel + paper tracker | _to write_ | charter only | 07c |
| 07e | Backtest harness (KILL-GATE) | _to write_ | charter only | 07d + backtest data source + survivorship handling |
| 07f | Self-improvement harness | _to write_ | charter only | 07e |
| — | Cross-venue orchestrator | _later plan_ | deferred | both funds have paper track records |

## Charters (scope only — NOT implementation plans)

### 07b — Screening
Build `equities/screen/swing_screen.py` (small/mid-cap: trend + relative-volume + catalyst window) and `quality_screen.py` (large-cap quality for DCA core). Input: a universe of `Instrument`. Output: ranked candidate `Instrument`s. **Research first:** concrete signal definitions, universe source + survivorship handling.

### 07c — Analyst engine
Build `equities/analysis/analyst.py`: two-stage Claude pipeline (Haiku filter ranks candidates → Sonnet writes thesis + sets entry/stop/take-profit on survivors), hard candidate cap + daily USD budget guard. Output: `Recommendation`s. **Research first:** prompt design, cost model, budget-guard mechanics. Mirrors the Polymarket LLM-probability bot.

### 07d — Risk kernel + paper tracker
Build `equities/risk/kernel.py` (IMMUTABLE sealed fuses: per-trade risk cap, max daily loss, max position size, total-drawdown circuit-breaker, auto-rollback hook), `risk/sizing.py` (shares from stop distance + risk cap), `risk/exits.py` (stop/target/time-stop), and `equities/paper.py` (records recs to `EquityLedger`, nightly mark-to-market, fires exits). The kernel is a frozen module the self-improvement harness has no write path to.

### 07e — Backtest harness (THE KILL-GATE)
Build `equities/backtest/`: walk-forward backtest over the real universe, net of a fee+slippage model. **Gate:** swing sleeve must show positive walk-forward expectancy net of costs. If not, the swing sleeve is killed before paper-trading. **Research first:** historical data source, survivorship bias handling, fee/slippage model.

### 07f — Self-improvement harness
Build `equities/improve/`: autonomous variant generation + tournament on walk-forward data, auto-promotion of winners to the real-capital book, auto-rollback on live degradation, Obsidian audit log. Bounded ONLY by the immutable risk kernel (per the spec's explicit eyes-open full-autonomy override). **Research first:** variant representation, promotion/rollback thresholds, walk-forward split policy.

### (Later) Cross-venue orchestrator
Generalize Plan 05 into the single allocator ("hedge-fund boss") that splits one real-capital pool across the Polymarket strategies and the equity `Fund`. Built last — only sensible once each fund has a real paper track record.
