# Plan 07 — Multi-Asset Analysis Bots (Stocks + Spot Crypto)

> **STATUS: DRAFT — REQUIREMENTS CAPTURE ONLY. NOT DESIGNED, NOT APPROVED, DO NOT IMPLEMENT FROM THIS STUB.**
> Captured 2026-05-31. Requires a `superpowers:brainstorming` session, then a full spec (00-SPEC style) + per-bot plans BEFORE any code.

## Requirement (from the user)
Extend the orchestrator so it also manages two NEW bots beyond Polymarket:
1. A **stock bot**, and
2. A **spot crypto bot**.

Each must **analyze the market**: ingest **news**, pull **company analytics / fundamentals**, fetch **price data**, **detect trends**, and produce **decisions** — including **entry, stop-loss, and take-profit** (these continuous-asset concepts ARE in scope here, unlike Polymarket).

Real-world context: the user can buy ~**1 share/month on Revolut** (e.g. IBM) and wants analysis-driven decisions.

## CRITICAL — this is a NEW DOMAIN, not a tweak
The current system (Plans 01–06) is **Polymarket-only**: binary event-outcome shares, Kelly-on-probability-vs-price, hold-to-resolution, no stops, no wallet, paper-only. Equities and spot crypto are fundamentally different:
- **Different venues / data:** no CLOB; need equity + crypto **price/OHLC**, **news**, and **fundamentals** feeds.
- **Different risk model:** continuous prices with real **stop-loss / take-profit / position management** — the Polymarket half-Kelly + 2%-cap-on-binary model does **NOT** map directly.
- **Naming clash:** Plan 04 ("crypto up/down") is Polymarket **prediction** markets, NOT spot crypto. This new crypto bot is a **different thing** — confirm scope with the user.

## OPEN DECISIONS the next planning session MUST resolve (do not assume)
1. **Allocator scope:** extend the existing capital-allocator orchestrator (Plan 05) to route across **heterogeneous venues** (Polymarket + equities + spot crypto), OR build a **separate** multi-asset system? Cross-venue capital allocation is a major generalization.
2. **Analyst vs automated trader:** Revolut has **no retail trading API** — so the stock bot is almost certainly an **analyst/advisor that outputs decisions the user executes manually**, not an automated executor. Confirm. (Spot crypto *could* be automated via exchange APIs later, but paper-first.)
3. **Regulatory framing:** stock/crypto recommendations are investment decisions. Must carry an explicit **"analysis, not licensed financial advice"** disclaimer; the user owns every trade. Confirm acceptable.
4. **Strategy coherence:** monthly **DCA (1 share/month)** vs **entry/SL/TP** are different philosophies and partly contradict each other (you don't stop-loss something you're systematically accumulating). Pick a coherent model **per asset / per goal**.
5. **Risk model for continuous assets:** define position sizing, stop-loss, take-profit, and max-drawdown rules from scratch — the Polymarket universal risk rules do **not** transfer.
6. **Paper-first + evidence-gating:** carry over the master-spec discipline — prove edge on paper/backtest before any real-money or live-decision use.

## Data feeds to RESEARCH in the spec phase (free-first per project ethos)
- **Equity price/OHLC:** Stooq, Yahoo (yfinance), Alpha Vantage / Finnhub free tiers (research current limits).
- **Crypto price/OHLC:** Binance / Coinbase public APIs, CoinGecko free.
- **News:** RSS, GDELT, NewsAPI free tier; per-ticker news from Finnhub.
- **Fundamentals / filings:** SEC EDGAR (US, free), Alpha Vantage / Finnhub fundamentals (free tiers).
- All TBD — paid feeds only after a strategy proves out (mirrors the master-spec free-data-first stance).
- **Claude itself** is the analysis engine (synthesize news + fundamentals + price action into a thesis), echoing the LLM-probability bot pattern but for continuous assets.

## Architecture stance (carry-over, NOT decided)
- Each new bot likely implements a **new Strategy-like protocol for CONTINUOUS assets** — the existing `core.strategy.Strategy` is binary-outcome-specific; do **not** force-fit it. A parallel `ContinuousStrategy` / `AnalysisBot` protocol is the likely shape.
- **Reuse where genuinely shared:** `Ledger` (already has a `strategy` column), `config`, `alerts` (Telegram), and the orchestrator allocator skeleton.
- Keep the **paper-trading + walk-forward / evidence-gated** discipline.
- The **self-improvement harness (Plan 06)**, once built, should be able to retune these bots' thresholds under the same bounded/validated rules.

## Next step
1. `superpowers:brainstorming` on this domain with the user (resolve the 6 open decisions above).
2. Write a proper spec + per-bot implementation plans (TDD, subagent-driven, like Plans 01–06).
3. Only then implement. **This file is requirements capture only.**
