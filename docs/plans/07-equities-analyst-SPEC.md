# Plan 07 — Equities Analyst Bot — SPEC

> **Status:** DESIGNED via `superpowers:brainstorming` (2026-05-31), **stress-tested via `/grill-me` (2026-06-01)**. Supersedes the requirements stub in `07-multi-asset-analysis-bots.md`. Scope narrowed: **US equities only** (spot crypto deferred to its own future spec).
> Next: TDD subagent-driven build (like Plans 01–06), starting at `07a-equity-foundation-PLAN.md` → `07-SPIKE` → 07b…07f.
> **Grill-me materially changed this spec** — see the "Grill-Resolved Revisions" section; the original brainstorm decisions below are annotated where superseded.

## Grill-Resolved Revisions (2026-06-01) — read these first

These supersede/extend the brainstorm decisions below where they conflict:

1. **Edge = synthesis, not speed** (Q1). Horizon 1–4 weeks; win on interpretation of complexity, not reaction time.
2. **Autonomy stays, but real-money promotion is math-gated** (Q2): kill-gate pass + min live-paper track record + cooldown rate-limit; risk kernel is a **separate guardian process**.
3. **Kill-gate = forward-paper-only** (Q3): ≥100 real-time paper trades net of costs. Historical backtest demoted to throwaway pre-filter (free data ⇒ unavoidable survivorship + lookahead bias).
4. **`07-SPIKE` inserted after Foundation** (Q4): prove Claude's synthesis on 10 hand-picked tickers before building screening/risk/backtest.
5. **Screen hunts EVENTS, not moves** (discovery): upcoming earnings, post-earnings drift, fresh filings. **Claude's #1 rule: reject already-fully-priced setups.**
6. **Risk = tight 1–2%** (fractional shares confirmed) + gap-aware stops + concurrency/concentration caps (Q5).
7. **Costs:** Revolut 0.25%/leg after 1 free trade/month + FX → rewards fewer, longer, high-conviction holds.
8. **Revolut = real resting orders** (limit buy / stop / limit sell); OCO/bracket support UNVERIFIED (confirm before 07d).

## Brainstorm-Resolved Decisions

1. **Role — phased.** Build an **analyst/advisor** first: it emits recommendations (thesis + entry/stop/take-profit) that the user executes manually on Revolut as **real resting orders** (limit buy = entry, stop order = stop-loss, limit sell = take-profit — see "Revolut Execution Reality"). An **automated broker executor** (Alpaca/IBKR — for a real API, which Revolut lacks) is bolted on **later**, behind a `LIVE=true` flag that does not exist yet, only after paper proves edge.
2. **Asset scope — US stocks only.** Spot crypto is a separate future spec (different venue, 24/7 market, different risk). Not in this build.
3. **Two sleeves, kept strictly separate** (resolves the DCA-vs-stops contradiction):
   - **Core sleeve (DCA):** large-cap quality, months–years horizon, **no stops**, systematic accumulation. Not edge-gated.
   - **Satellite sleeve (Swing):** under-covered small/mid-cap, days–weeks horizon, **hard stop-loss + take-profit + time-stop**. Edge-gated.
4. **Edge thesis (HYPOTHESIS, not belief) — `[REVISED BY GRILL Q1: synthesis, not speed]`.** ~~"react within hours before the slow crowd"~~ is rejected — you will lose any reaction-speed race (no API, free/delayed feeds, fast prop shops live in small-caps). The honest edge is **synthesis of complexity over a 1–4 week horizon**: in small/mid-caps the thin analyst crowd is slow to *digest* a complex story buried in filings/calls, and Claude's interpretation gets a position before the re-rating completes. **NOT** a speed claim, **NOT** a claim to beat institutions/HFTs — a claim that *the sharpest competition is absent* and *the story is under-analyzed*. The forward-paper kill-gate is the honest arbiter.
5. **Universe — mix:** large-cap for the DCA core (safety), under-covered small/mid-cap for the swing sleeve (edge).
6. **Manager — unified, built last.** End-state: the single `orchestrator/` ("hedge-fund boss") allocates one real-capital pool across **both** Polymarket strategies and the equity fund (and future crypto). The equity fund exposes a standard **fund interface** (reports positions/PnL/exposure, accepts an allocation) so the orchestrator can manage it. The cross-venue allocator is built **last** (later plan, generalizing Plan 05) — it can only sensibly split capital once each fund has a real paper track record. During the paper phase each fund runs on its own notional book.
7. **Per-trade risk cap — `[REVISED BY GRILL Q5: fractional shares confirmed → tight 1–2%]`.** Revolut **supports fractional shares** (confirmed by user), so position size is *continuous* — a tight cap is honorable even at $500. Cap = **2% now** (~$10/trade), ratcheting → 1% above ~$1.5k. Risk % scales variance, **not** edge. PLUS (Q5) the kernel adds a **concurrent-position cap** (≤ ~4 swing positions) and a **per-name concentration cap** (no single name > ~25% of the swing sleeve) — the per-trade fuse alone still allows over-concentration. AND the cost/fill model must be **gap-aware**: Revolut stop orders become *market* orders when hit, so they fill *worse* than the stop on a gap (confirmed behaviour) — model stop fills at stop-minus-penalty so paper results don't lie.
8. **Self-improvement — fully autonomous, `[REVISED BY GRILL Q2: evidence-gated promotion + guardian process]`.** Still fully autonomous self-rewriting with **no per-trade human approval** (user's choice preserved). But real-money exposure is gated by **math, not a human**: a self-rewritten variant runs **unbounded on the paper book forever**, and may **auto-promote to the real-capital book only after** (a) clearing the forward-paper kill-gate AND (b) accumulating a minimum live-paper track record, AND (c) a **cooldown rate-limit** (≤ one new real-money version per N weeks) so the overfit-churn loop cannot keep refunding lucky variants. The immutable risk kernel runs as a **separate guardian process** the strategy/rewriter code cannot import, write, or disable. This still overrides the master-spec's human-approval principle (deliberate, eyes-open) — but the acknowledged risks (overfitting, silent drift) are now bounded by evidence-volume + cooldown + an out-of-process kernel, not just a per-trade fuse.

## Hard Constraints

- **Language/stack:** reuse the existing Python 3.12 / `uv` monorepo. Reuse `core.config`, `core.ledger` pattern, `core.alerts.telegram`. Do **not** force-fit binary Polymarket types (`Signal`/`Fill`/`Market`) — equities get parallel continuous-asset types.
- **Money:** paper-only until the swing kill-gate passes. No broker credentials, no live orders, no `LIVE` code in this milestone.
- **Data:** free feeds first (yfinance/Stooq prices, SEC EDGAR fundamentals, RSS/Finnhub-free news, earnings calendar). Paid feeds only after a sleeve proves out.
- **Analysis engine = Claude**, two-stage cheap(Haiku-filter)→Sonnet(deep thesis), hard candidate cap + daily USD budget guard (mirrors the LLM-probability bot).

## Immutable Risk Kernel (sealed fuses — self-rewriting code CANNOT modify these)

Even under full autonomy, the strategy layer physically cannot disable or breach:
- **Max loss per trade:** the parameterized risk cap (2%→1%), measured **gap-aware** (stop fills at stop-minus-penalty).
- **Max concurrent positions** (Q5): ≤ ~4 swing positions open at once.
- **Per-name concentration cap** (Q5): no single name > ~25% of the swing sleeve.
- **Max total daily loss:** halts new entries for the day when breached.
- **Max single-position size:** hard ceiling as % of capital.
- **Total-drawdown circuit-breaker:** halts ALL trading when account drawdown from high-water mark exceeds a hard threshold.
- **Real-money promotion gate** (Q2): a variant reaches the real-capital book only after kill-gate pass + minimum live-paper track record + cooldown rate-limit.
- **Auto-rollback:** a promoted version whose live performance degrades past a threshold auto-reverts to the last good version.

**The kernel runs as a SEPARATE GUARDIAN PROCESS** (Q2) — not an in-process module — that the strategy code and the self-rewriter cannot import, write to, or disable. "Immutable" is enforced by process/file isolation, not a comment. Full autonomy lives *inside* this fuse box.

## Architecture

```
polymarket-bot/
├── core/                      # EXISTING — reused
│   ├── config.py  ledger.py  alerts/telegram.py
│   └── assets/                # NEW shared continuous-asset domain
│       ├── instrument.py      # Instrument(ticker, name, exchange, cap_tier)
│       ├── bar.py             # OHLCV price-series types
│       └── position.py        # continuous Position (entry/stop/target/sleeve)
├── equities/                  # NEW equity fund
│   ├── data/                  # free-first feeds
│   │   ├── prices.py          # OHLCV: yfinance / Stooq
│   │   ├── news.py            # per-ticker news: RSS / Finnhub-free
│   │   ├── fundamentals.py    # SEC EDGAR (free) / Finnhub
│   │   └── calendar.py        # earnings dates
│   ├── screen/
│   │   ├── swing_screen.py    # small/mid-cap: trend + volume + catalyst
│   │   └── quality_screen.py  # large-cap quality for DCA core
│   ├── analysis/analyst.py    # Claude two-stage Haiku→Sonnet + $ budget guard
│   ├── risk/
│   │   ├── kernel.py          # IMMUTABLE risk kernel (sealed fuses)
│   │   ├── sizing.py          # position size from stop distance + risk cap
│   │   └── exits.py           # stop-loss / take-profit / time-stop
│   ├── strategy.py            # ContinuousStrategy protocol + Recommendation type
│   ├── fund.py                # Fund interface (positions/PnL/exposure/allocation)
│   ├── paper.py               # paper tracker: mark-to-market, trigger exits, PnL
│   ├── ledger_equity.py       # EquityLedger (continuous-position schema)
│   ├── backtest/              # walk-forward harness = the KILL-GATE
│   └── improve/               # autonomous self-improvement harness
├── orchestrator/              # FUTURE cross-venue allocator (hedge-fund boss)
└── runner_equities.py         # entrypoint
```

### New domain types (parallel to `Signal`/`Fill`, NOT reused)
- `Recommendation` — instrument, sleeve (`core`|`swing`), side, entry, stop_loss, take_profit, size_pct, confidence, catalyst, thesis, horizon.
- `ContinuousStrategy` protocol — `scan(universe) -> list[Recommendation]`.
- `Fund` interface — `positions()`, `pnl()`, `exposure()`, `set_allocation(usd)` — the contract the future orchestrator consumes (Polymarket strategies get wrapped in the same interface).

### Ledger decision
The existing `Ledger` is binary-outcome-shaped (`token_id`, `fair_prob`, `condition_id`, `won`, `resolved`) — wrong shape for continuous positions. Build a **parallel `EquityLedger`** reusing the sqlite-file + CSV pattern and the `strategy` column convention, with a proper continuous-position schema (entry, stop, target, shares, mark price, unrealized/realized PnL, sleeve, status).

### Data flow
screen universe → fetch prices/news/fundamentals/earnings per candidate → two-stage analysis (Haiku filter ranks → Sonnet writes thesis + sets entry/SL/TP on survivors) → risk layer sizes & validates against the kernel → record to `EquityLedger` + Telegram alert with the exact action → nightly mark-to-market updates PnL and fires exit triggers.

## Build Order (each milestone shippable + testable, TDD)

1. **Equity Foundation (07a)** — `core/assets/` types, `EquityLedger`, **prices feed only** (news/fundamentals/earnings deferred to where they're researched), config + Telegram reuse, `Fund` interface skeleton.
2. **`07-SPIKE` — synthesis proof `[ADDED BY GRILL Q4]`.** Throwaway, ~1 day: hardcode ~10 catalyst tickers, pull real filings+news, hand to Claude with the analyst prompt, print 10 recommendations + eyeball them (optionally forward-paper-track 2–4 wks). **Kills the project cheaply if Claude's synthesis is garbage — BEFORE building the machine.** No tests, deleted after.
3. **Screening (07b) — hunt EVENTS, not moves `[REVISED BY GRILL: discovery]`.** Mechanical screen surfaces *catalysts where re-rating may be incomplete*: upcoming earnings dates, recent earnings *surprises* (post-earnings-announcement drift), fresh 8-Ks/filings. Claude — not the screen — is the analyst; the screen is just the cheap funnel.
4. **Analyst engine (07c)** — two-stage Haiku→Sonnet thesis + entry/SL/TP, daily $ budget guard. **Claude's #1 rule: REJECT setups already fully priced** (encodes the "already moved = too late" insight).
5. **Risk + paper tracker (07d)** — guardian-process risk kernel, gap-aware sizing, exits, concurrency/concentration caps, mark-to-market PnL.
6. **Forward-paper instrumentation + (throwaway) mechanical pre-filter (07e) `[REVISED BY GRILL Q3]`** — the **kill-gate is forward-paper-only**; a cheap price-only backtest stays as a disposable pre-filter, NOT the trust oracle.
7. **Self-improvement harness (07f)** — autonomous variant tournament, evidence+cooldown-gated auto-promote, auto-rollback, Obsidian audit log.
8. *(Later)* **Cross-venue orchestrator** — unify Polymarket + equities under one allocator.

## Evidence Gates (kill-gates) `[REVISED BY GRILL Q3: forward-paper-only]`

- **Swing go-live bar = forward-paper-only:** **≥100 real-time forward paper trades, positive expectancy net of the cost model** (0.25%/leg + FX + gap-aware slippage). Forward paper is structurally immune to survivorship + lookahead bias, which free data makes unavoidable in any historical backtest of an LLM-synthesis strategy. Slow (likely months) — that is the honest price of an honest gate.
- **Historical backtest = throwaway pre-filter only**, never the trust oracle (price-only mechanical sanity check, survivorship caveat stamped on it).
- **Synthesis spike (`07-SPIKE`) is the *earliest* gate:** if Claude's analysis is obviously garbage on 10 hand-picked tickers, stop before building 07b+.
- **Core (DCA):** not edge-gated (accumulation), but paper-tracked.
- **Automation gate:** broker executor ships behind a `LIVE=true` flag that does not exist yet; manual execution until paper proves out.

## Revolut Execution Reality `[ADDED BY GRILL Q5 + research]`

The manual phase places **real resting orders** on Revolut (not just alerts):

| Bot output | Revolut order |
|---|---|
| Entry | **Limit buy** |
| Stop-loss | **Stop order** (sell) — becomes a *market* order when hit → gap slippage (model it) |
| Take-profit | **Limit sell** (Revolut has no native stock "take-profit" label, but a limit sell is equivalent) |

- **Fractional shares: YES** → precise sizing, tight 1–2% risk is honorable at $500.
- **Cost model:** **1 commission-free trade/month, then 0.25% per trade** + FX. Round-trip ≈ 0.5%+ → *punishes churn, rewards fewer high-conviction multi-week holds.* Bake into the kill-gate cost model.
- **UNVERIFIED — confirm in-app before 07d:** whether a stop + a limit-sell can attach to the *same* shares as a one-cancels-other (OCO/bracket); if not, manual cancel of the other leg after one fills.

## Open Items for the Spec/Plan Phase (research before coding)
- Exact free data feeds + current rate limits (yfinance vs Stooq reliability; SEC EDGAR endpoints; Finnhub free tier; earnings-calendar source).
- Concrete **event** screen definitions (Q-driven): earnings-date proximity, earnings-surprise magnitude for PEAD, fresh-8-K detection.
- **Forward-paper instrumentation** (the gate) + the disposable price-only pre-filter — NOT a survivorship-free historical backtest.
- **Cost model:** Revolut 0.25%/leg + FX + **gap-aware** stop fills (stop-minus-penalty) for the simulated fills.
- `EquityLedger` exact schema (done in 07a).
- Self-improvement harness mechanics: variant representation, **promotion gate (kill-gate + min live-paper + cooldown)**, rollback thresholds, walk-forward split policy.
- **Guardian-process** design for the risk kernel (how it runs out-of-process and how the strategy/rewriter is denied write access).

## Verification Items (user confirms before 07d)
- Revolut OCO/bracket: can a stop + limit-sell attach to the same shares (one-cancels-other)? If not, manual cancel of the surviving leg.
- Confirm current Revolut commission/FX exactly matches the cost model (1 free/month, then 0.25%/leg).
