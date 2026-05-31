# Plan 07 — Equities Analyst Bot — SPEC

> **Status:** DESIGNED via `superpowers:brainstorming` (2026-05-31). Supersedes the requirements stub in `07-multi-asset-analysis-bots.md`. Scope narrowed: **US equities only** (spot crypto deferred to its own future spec).
> Next: `superpowers:writing-plans` → per-milestone plans → `/grill-me` stress test → TDD subagent-driven build (like Plans 01–06).

## Brainstorm-Resolved Decisions

1. **Role — phased.** Build an **analyst/advisor** first: it emits recommendations (thesis + entry/stop/take-profit) that the user executes manually. An **automated broker executor** (Alpaca/IBKR — *not* Revolut, which has no retail API) is bolted on **later**, behind a `LIVE=true` flag that does not exist yet, only after paper proves edge.
2. **Asset scope — US stocks only.** Spot crypto is a separate future spec (different venue, 24/7 market, different risk). Not in this build.
3. **Two sleeves, kept strictly separate** (resolves the DCA-vs-stops contradiction):
   - **Core sleeve (DCA):** large-cap quality, months–years horizon, **no stops**, systematic accumulation. Not edge-gated.
   - **Satellite sleeve (Swing):** under-covered small/mid-cap, days–weeks horizon, **hard stop-loss + take-profit + time-stop**. Edge-gated.
4. **Edge thesis (HYPOTHESIS, not belief):** in small/mid-caps big funds ignore, news/earnings information diffuses slowly; a disciplined analyst reacting within hours with strict risk rules can capture moves before the slow retail crowd. **NOT** a claim to beat institutions/HFTs — a claim that *the sharpest competition is absent* in these names. Equity analogue of the Polymarket "thin illiquid markets" thesis.
5. **Universe — mix:** large-cap for the DCA core (safety), under-covered small/mid-cap for the swing sleeve (edge).
6. **Manager — unified, built last.** End-state: the single `orchestrator/` ("hedge-fund boss") allocates one real-capital pool across **both** Polymarket strategies and the equity fund (and future crypto). The equity fund exposes a standard **fund interface** (reports positions/PnL/exposure, accepts an allocation) so the orchestrator can manage it. The cross-venue allocator is built **last** (later plan, generalizing Plan 05) — it can only sensibly split capital once each fund has a real paper track record. During the paper phase each fund runs on its own notional book.
7. **Per-trade risk cap = 3% now, parameterized + ratcheting.** At $500 starting capital, 3% (~$15 max loss/trade) is the loosest *disciplined* cap that lets whole shares trade (~23 straight losses to halve the account). Ratchets down automatically: → 2% above ~$1.5k, → 1% with fractional shares or ~$3k+. Risk % scales variance, **not** edge — profit comes from the strategy, not the size.
8. **Self-improvement — fully autonomous on real money (explicit, eyes-open override).** The user explicitly chose unbounded autonomous self-rewriting that promotes new strategy versions to the **real-capital** book without per-change human approval. This **overrides** the master-spec principle ("improvement must be earned with out-of-sample evidence; structural changes require human approval"). Documented here as a deliberate, informed decision. The acknowledged risks: overfitting to noise, silent capital drift. Mitigated **only** by the immutable risk kernel + auto-rollback below (automated fuses, not human gating).

## Hard Constraints

- **Language/stack:** reuse the existing Python 3.12 / `uv` monorepo. Reuse `core.config`, `core.ledger` pattern, `core.alerts.telegram`. Do **not** force-fit binary Polymarket types (`Signal`/`Fill`/`Market`) — equities get parallel continuous-asset types.
- **Money:** paper-only until the swing kill-gate passes. No broker credentials, no live orders, no `LIVE` code in this milestone.
- **Data:** free feeds first (yfinance/Stooq prices, SEC EDGAR fundamentals, RSS/Finnhub-free news, earnings calendar). Paid feeds only after a sleeve proves out.
- **Analysis engine = Claude**, two-stage cheap(Haiku-filter)→Sonnet(deep thesis), hard candidate cap + daily USD budget guard (mirrors the LLM-probability bot).

## Immutable Risk Kernel (sealed fuses — self-rewriting code CANNOT modify these)

Even under full autonomy, the strategy layer physically cannot disable or breach:
- **Max loss per trade:** the parameterized risk cap (3%→1%).
- **Max total daily loss:** halts new entries for the day when breached.
- **Max single-position size:** hard ceiling as % of capital.
- **Total-drawdown circuit-breaker:** halts ALL trading when account drawdown from high-water mark exceeds a hard threshold.
- **Auto-rollback:** a promoted version whose live performance degrades past a threshold auto-reverts to the last good version.

The kernel is a separate, frozen module the improvement harness has no write path to. Full autonomy lives *inside* this fuse box.

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

1. **Equity Foundation** — `core/assets/` types, `EquityLedger`, data feeds, config + Telegram reuse, `Fund` interface skeleton.
2. **Screening** — swing + quality screens over the universe.
3. **Analyst engine** — two-stage Haiku→Sonnet thesis + entry/SL/TP, daily $ budget guard.
4. **Risk + paper tracker** — risk kernel, sizing, exits, mark-to-market PnL.
5. **Backtest harness** — walk-forward = the kill-gate.
6. **Self-improvement harness** — autonomous variant tournament, auto-promote, auto-rollback, Obsidian audit log.
7. *(Later)* **Cross-venue orchestrator** — unify Polymarket + equities under one allocator.

## Evidence Gates (kill-gates)

- **Swing go-live bar:** positive walk-forward backtest expectancy **net of fees + slippage** AND ≥100 paper trades with positive ROI → only then eligible for real capital. If the backtest shows no edge, **the swing sleeve is killed before it paper-trades.** No sunk-cost continuation.
- **Core (DCA):** not edge-gated (accumulation), but paper-tracked.
- **Automation gate:** broker executor ships behind a `LIVE=true` flag that does not exist yet; manual execution until paper proves out.

## Open Items for the Spec/Plan Phase (research before coding)
- Exact free data feeds + current rate limits (yfinance vs Stooq reliability; SEC EDGAR endpoints; Finnhub free tier; earnings-calendar source).
- Concrete swing-screen signal definitions (trend, relative volume, catalyst windows around earnings).
- Backtest data source + survivorship-bias handling for the small/mid-cap universe.
- Slippage/fee model for the simulated fills.
- `EquityLedger` exact schema.
- Self-improvement harness mechanics (what a "variant" is, promotion/rollback thresholds, walk-forward split policy).
