# polymarket-bot

An autonomous paper-trading research system for [Polymarket](https://polymarket.com) prediction markets and US equities. All LLM analysis routes through your **Claude subscription** via `claude -p` — no Anthropic API key required.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Equities Pipeline (detailed)](#equities-pipeline-detailed)
  - [Macro Regime Classification](#macro-regime-classification)
  - [Screening Layer](#screening-layer)
  - [4-Stage LLM Analysis](#4-stage-llm-analysis)
  - [Signal Fusion & Dynamic Sizing](#signal-fusion--dynamic-sizing)
  - [Risk Kernel](#risk-kernel)
  - [Data Providers](#data-providers)
  - [Research Intelligence](#research-intelligence)
  - [Killgate & Position Monitoring](#killgate--position-monitoring)
- [Polymarket Pipeline](#polymarket-pipeline)
- [Plans & Milestones](#plans--milestones)
- [Prerequisites & Setup](#prerequisites--setup)
- [Running](#running)
- [LLM Routing](#llm-routing)
- [Key Design Decisions](#key-design-decisions)
- [Repository Structure](#repository-structure)

---

## Architecture Overview

```
runner.py                   ← Polymarket orchestrated runner
runner_equities.py          ← US equities paper runner (primary)
runner_research.py          ← Weekly offline research runner

strategies/
  llm_probability/          ← Haiku prefilter → Sonnet edge estimate
  weather/                  ← NWS forecast vs. market consensus
  crypto_updown/            ← BTC spot/CLOB arb + repricing

orchestrator/               ← Multi-strategy capital allocation + risk gate
harness/                    ← Nightly self-improvement (calibration, retuning, vault)

equities/
  data/                     ← Price feed, fundamentals, news, VIX, macro regime
  screen/                   ← Event screen, quality screen, inflection screen, thematic monitor
  analysis/                 ← 4-stage LLM pipeline (Haiku prefilter → Sonnet analyst
  │                            → Sonnet challenger → Sonnet auditor)
  risk/                     ← Gap-adjusted sizing, sector concentration, exit signals
  killgate/                 ← Forward paper tracker, thesis health checker
  research/                 ← Supply chain graph, discovery lag, thesis miner,
                               narrative gap detector

core/
  claude_client.py          ← ClaudeCodeClient (`claude -p` subprocess wrapper)
  clob/                     ← Polymarket CLOB WebSocket + Gamma REST client
  ledger.py                 ← Trade ledger with PnL tracking (SQLite)
  execution/paper.py        ← Paper executor with slippage + fee model
```

---

## Equities Pipeline (detailed)

`runner_equities.py` runs the full end-to-end loop on every invocation:

```
1. Mark-to-market + exit checks
2. Macro regime classification
3. Thesis health check (open swing positions)
4. Thematic concentration check
5. Swing screen (earnings / 8-K events)
6. Core screen (quality fundamentals)
7. Inflection screen (profitability crossover candidates)
8. [--no-analyse exits here]
9. VIX regime gate
10. 4-stage LLM analyst (prefilter → analyst → challenger → auditor)
11. Signal fusion → size tier
12. Risk kernel → paper open
```

---

### Macro Regime Classification

**File:** `equities/data/macro_regime.py`

Classifies the current macro environment from five yfinance signals before any analysis runs. The regime is printed at startup and injected into every analyst prompt.

| Signal | Ticker | Use |
|--------|--------|-----|
| Volatility | `^VIX` | Fear gauge |
| Yield curve | `^TNX − ^IRX` (10y − 3m) | Recession signal |
| Credit spread | `HYG / LQD` ratio + 4-week trend | Risk appetite |
| Dollar strength | `DX-Y.NYB` | Macro headwind/tailwind |
| Sector momentum | `XLK, XLF, XLE, XLV` 4-week returns | Rotation |

**Regime rules (evaluated in order):**

| Regime | Condition |
|--------|-----------|
| `crisis` | VIX > 30 |
| `risk_off` | VIX > 22 **OR** yield curve < −0.20 **OR** HYG/LQD ratio dropping fast (< −1% over 4 weeks) |
| `risk_on` | VIX < 16 **AND** yield curve > 0.50 **AND** credit spread stable or rising |
| `neutral` | Everything else |

**Regime feeds into signal fusion** — `risk_off` tightens conviction thresholds by +0.10 (harder to size up), `risk_on` loosens by −0.05. The regime label, VIX level, and yield curve spread are also injected verbatim into the Sonnet analyst prompt so the model can factor macro context into its thesis.

Fails open on any network/data error — defaults to `neutral` regime.

---

### Screening Layer

#### Event Screen (`equities/screen/event_screen.py`)
Scans the universe for upcoming earnings (next 5 days) and recent 8-K SEC filings. Returns `CandidateEvent` objects with urgency scores.

#### Quality Screen (`equities/screen/quality_screen.py`)
Scores large-cap names on fundamentals: gross margins, trailing P/E, revenue growth YoY. Selects the top candidates for the core DCA sleeve.

#### Inflection Screen (`equities/screen/inflection_screen.py`)
**New in upgrade.** Identifies stocks that are 1–2 quarters from GAAP profitability. Looks for companies with:
- Negative trailing EPS but improving quarter-over-quarter
- Revenue growing >20% YoY
- Gross margins > 40% (unit economics proven)
- Implied quarters-to-profit ≤ 2

These are high-asymmetry setups: the market often ignores profitability inflections until the quarter they flip.

#### Thematic Monitor (`equities/screen/thematic_monitor.py`)
**New in upgrade.** Checks open positions against the supply chain graph (`equities/research/supply_chain.py`) for theme over-concentration. A single supply chain theme (e.g. NVDA supply chain) can have many tickers — if total exposure across all leaves of a theme exceeds `max_theme_pct` of capital, an alert is raised. Full position value is attributed to each theme the ticker belongs to (conservative / worst-case).

---

### 4-Stage LLM Analysis

The core analysis pipeline uses four sequential LLM calls per candidate. Each stage can veto.

```
Stage 1 — Haiku Prefilter
  Input : all screened candidates + analyst coverage counts
  Task  : rank by information-asymmetry score, reject obvious misses
  Output: ranked shortlist (max_candidates, default 5)
  Cost  : ~$0.002/batch

Stage 2 — Sonnet Analyst
  Input : single candidate + price + 8 headlines + 5 SEC filings
          + sector + analyst coverage + macro regime context
  Task  : identify if catalyst is unpriced; output entry/stop/TP/confidence/thesis
  Output: Recommendation or reject
  Cost  : ~$0.004/candidate

Stage 3 — Sonnet Challenger
  Input : Stage 2 recommendation
  Task  : steelman the bear case; generate specific objections
  Output: adjusted Recommendation (may lower confidence) + list[objections]
  Cost  : ~$0.004/candidate

Stage 4 — Sonnet Auditor
  Input : Stage 3 recommendation + objections
  Task  : score logical consistency of bull vs. bear; apply consistency penalty
  Output: final Recommendation with audited confidence, or None (veto)
  Cost  : ~$0.006/candidate
```

**Total cost per surviving candidate:** ~$0.014 — effectively free under Claude subscription.

The analyst prompt includes a `## Macro context` block:
```
Regime: neutral | VIX: 18.3 | Yield curve (10y-3m): 0.42
```

---

### Signal Fusion & Dynamic Sizing

**File:** `equities/analysis/analyst.py` → `_compute_build_action()`

After the 4-stage pipeline produces an audited confidence score, signal fusion maps it to a size tier. Regime offsets are applied first:

```
regime_offset = +0.10 if risk_off else (-0.05 if risk_on else 0.0)
adjusted_confidence = audited_confidence + consistency_penalty + regime_offset
```

| Tier | Threshold (adjusted) | Size |
|------|---------------------|------|
| `AGGRESSIVE_BUILD` | ≥ 0.75 | 4% of capital |
| `GRADUAL_BUILD` | ≥ 0.60 | 2% of capital |
| `NIBBLE` | ≥ 0.45 | 1% of capital |
| `WAIT` | < 0.45 | 0% (skipped) |

In `risk_off` regime, a confidence of 0.72 that would normally trigger `AGGRESSIVE_BUILD` gets adjusted to 0.82 (threshold raised), requiring genuinely high conviction. In `risk_on`, the same 0.72 gets adjusted to 0.67 — still `GRADUAL_BUILD` but the loosening allows more trades through.

---

### Risk Kernel

**File:** `equities/risk/kernel.py`

Final gate before paper execution. Checks:

1. **Concentration cap** — no single position > `max_position_pct` of capital (default 5%)
2. **Sector concentration** — no single GICS sector > `max_sector_pct` of portfolio (default 35%). Requires a `sector_lookup` dict mapping ticker → sector.
3. **Gap-aware sizing** — adjusts share count for overnight gap risk
4. **Open position count** — max simultaneous positions
5. **Stop-loss validity** — rejects if stop is above entry (long) or entry is invalid

---

### Data Providers

#### Fundamentals (`equities/data/fundamentals.py`)

`FundamentalsSnapshot` now carries 6 additional fields beyond the base set:

| Field | Source | Use |
|-------|--------|-----|
| `eps_trend` | yfinance | EPS quarter-over-quarter trend (list of floats) |
| `short_interest_pct` | yfinance | Short float % — contrarian signal |
| `peg_ratio` | yfinance | Growth-adjusted valuation |
| `operating_margins` | yfinance | Profitability quality |
| `debt_to_equity` | yfinance | Balance sheet risk |
| `free_cash_flow_m` | yfinance | FCF in millions |

#### News (`equities/data/`)

Three-tier news system:

- **`YFinanceNewsProvider`** — existing yfinance news scraper
- **`TiingoNewsProvider`** (`news_tiingo.py`) — Tiingo REST API; no-ops silently if `TIINGO_API_KEY` is absent
- **`CompositeNewsProvider`** (`news_composite.py`) — merges both providers, deduplicates by normalized headline, caps at requested limit

#### VIX Gate (`equities/data/vix.py`)

`VIXRegimeGate` fetches the current VIX and returns `(entries_allowed: bool, vix: float | None)`. If VIX > `threshold` (default 30), new entries are blocked and the runner exits after mark-to-market. Fails open on any error.

#### Macro Regime (`equities/data/macro_regime.py`)

See [Macro Regime Classification](#macro-regime-classification) above.

---

### Research Intelligence

**Directory:** `equities/research/`

Offline research modules — used by `runner_research.py` (weekly cron) rather than the daily runner.

#### Supply Chain Graph (`supply_chain.py`)

A static adjacency dict mapping "trunk" megacap companies to their "leaf" supply chain beneficiaries:

```python
SUPPLY_CHAIN = {
    "NVDA": ["COHR", "LITE", "FN", "ALAB", "MU", "KLIC", "ONTO", "AMKR", ...],
    "AMD":  ["MU", "KLIC", "AMKR", ...],
    "AVGO": ["COHR", "MRVL", "AMKR", ...],
    "MSFT": ["CRWD", "CRM", "NOW", ...],
    ...
}
```

**`BottleneckScorer`** ranks leaves by how many trunks they serve — the more supply chains a component touches, the harder it is to substitute.

Helper functions:
- `get_leaves_for_trunk(trunk)` → list of leaf tickers
- `get_trunks_for_leaf(leaf)` → list of trunk tickers

#### Discovery Lag Calculator (`discovery_lag.py`)

Quantifies the "discovery gap": trunk 12-month return minus leaf 12-month return. A large positive lag means the leaf hasn't caught up to the trunk's re-rating — a potential mispricing signal.

```
discovery_lag = trunk_12m_return − leaf_12m_return
```

High lag + high bottleneck score = strong candidate for the research pipeline.

#### Thesis Miner (`thesis_miner.py`)

Uses Haiku LLM to generate supply chain beneficiaries from high-level structural investment theses (e.g. "AI infrastructure buildout", "Electrification of transport"). Ships with a `STRUCTURAL_THESES` list of 10 macro themes.

```python
ThesisResult(thesis, beneficiaries=["KLIC", "ONTO", ...], reasoning="...")
```

Runs weekly — outputs a ranked list of tickers to add to the swing universe for further screening.

#### Narrative Gap Detector (`narrative_gap.py`)

Vocabulary-shift signal: compares recent news headline vocabulary for a ticker against a historical baseline. A surge in novel vocabulary (new technical terms, new analyst framing) often precedes a re-rating before it shows up in price.

Uses normalized term-frequency comparison and Jaccard distance.

#### Weekly Research Runner (`runner_research.py`)

```bash
uv run python runner_research.py
```

Orchestrates the offline research loop:
1. Runs `ThesisMiner` on all structural theses → new ticker candidates
2. Scores candidates with `DiscoveryLagCalculator`
3. Prints ranked opportunity list + bottleneck scores

Run weekly; output informs manual updates to `DEFAULT_SWING_UNIVERSE`.

---

### Killgate & Position Monitoring

#### Thesis Health Checker (`equities/killgate/thesis_health.py`)

Nightly review of all open **swing** positions. For each position, fetches 10 recent headlines and asks Haiku LLM:

> Is the original entry thesis still intact, degraded, or invalidated?

Returns a `ThesisHealth` dataclass:

| Field | Values |
|-------|--------|
| `status` | `intact` / `degraded` / `invalidated` |
| `action` | `hold` / `reduce` / `exit` |
| `reason` | One-sentence explanation |

`action == "exit"` triggers a Telegram alert. Fails open (defaults to `hold`) on any LLM or network error.

#### Forward Paper Tracker (`equities/killgate/tracker.py`)

Records every paper entry. Kill-gate condition: ≥ 100 forward-paper trades **and** positive net PnL after simulated 0.25%/leg Revolut cost and 2% overnight gap penalty. Real capital deployment is gated on this.

---

## Polymarket Pipeline

Three strategies, all paper-only until kill-gate clears:

### LLM Probability (`strategies/llm_probability/`)
- Haiku prefilter scores all open markets by edge potential
- Sonnet produces calibrated probability estimate + confidence interval
- Kelly-sized position if edge > min_edge threshold

### Weather (`strategies/weather/`)
- Fetches NWS multi-model ensemble forecast
- Compares to implied market probability
- Bets when model consensus diverges > threshold from market

### Crypto Up/Down (`strategies/crypto_updown/`)
- BTC spot feed via CLOB WebSocket
- Detects arbitrage when YES + NO implied prices sum < 1 − fee
- Optional directional repricing if latency probe shows median lag < 500ms

### Orchestrator (`orchestrator/`)
Performance-weighted capital allocation across all three strategies. Nightly reconcile, drawdown circuit breaker, strategy-level risk gate.

---

## Plans & Milestones

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
| 08 | Research & analysis upgrade (15-task plan — details below) | ✅ |

### Plan 08 — Research & Analysis Upgrade

| Task | Module | Description |
|------|--------|-------------|
| 1 | `analysis/analyst.py` | Auditor agent (Stage 4): consistency penalty, veto capability |
| 2 | `analysis/analyst.py` | Signal fusion: AGGRESSIVE/GRADUAL/NIBBLE/WAIT with dynamic sizing |
| 3 | `analysis/prompt.py` | Inject sector + analyst coverage count into analyst prompt |
| 4 | `risk/kernel.py` | Sector concentration cap (`max_sector_pct`) |
| 5 | `data/fundamentals.py` | Enrich `FundamentalsSnapshot` with 6 new financial metrics |
| 6 | `data/news_tiingo.py` + `news_composite.py` | Multi-source news with deduplication |
| 7 | `data/vix.py` | VIX regime gate — block entries above threshold |
| 8 | `screen/inflection_screen.py` | Profitability crossover screen |
| 9 | `research/supply_chain.py` | Supply chain graph + bottleneck scorer |
| 10 | `research/discovery_lag.py` | Discovery lag calculator (trunk vs. leaf return delta) |
| 11 | `research/thesis_miner.py` | LLM structural thesis → beneficiary candidates |
| 12 | `research/narrative_gap.py` | Vocabulary-shift narrative gap detector |
| 13 | `killgate/thesis_health.py` | Nightly thesis health checker (Haiku LLM) |
| 14 | `screen/thematic_monitor.py` | Supply chain theme concentration monitor |
| 15 | `data/macro_regime.py` | 5-signal macro regime gate (crisis/risk_off/neutral/risk_on) |

---

## Prerequisites & Setup

**Requirements:**
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- [Claude Code CLI](https://claude.ai/code) — logged in with an active Claude subscription
- ProtonVPN (or equivalent) when running Polymarket strategies — geo-blocked in some regions

**Install:**

```bash
git clone https://github.com/nikolas-sapa/polymarket-bot.git
cd polymarket-bot
uv sync
cp .env.example .env
```

**Optional env vars** (all have safe fallbacks if absent):

| Variable | Purpose | Fallback |
|----------|---------|----------|
| `TIINGO_API_KEY` | Extra news source via Tiingo | No-op, uses yfinance only |
| `TELEGRAM_BOT_TOKEN` | Trade alert notifications | Alerts silently disabled |
| `TELEGRAM_CHAT_ID` | Telegram destination chat | Alerts silently disabled |

No Anthropic API key needed. All LLM calls go through `claude -p`.

---

## Running

### Equities paper runner

```bash
# Full pass: screen all universes + 4-stage LLM analysis + paper open
uv run python runner_equities.py

# Screen only — no LLM calls, no Claude API usage
uv run python runner_equities.py --no-analyse

# Mark-to-market + exit checks only
uv run python runner_equities.py --mark-only
```

### Weekly research runner

```bash
# Offline: thesis mining + discovery lag scoring
# Outputs ranked candidate list — no trades, no LLM analysis pipeline
uv run python runner_research.py
```

### Polymarket — all strategies, orchestrated

```bash
PYTHONPATH=. uv run python runner.py --strategy llm,weather,crypto_updown --mode orchestrated
```

### Polymarket — single strategy

```bash
PYTHONPATH=. uv run python runner.py --strategy weather --mode simple
```

### Latency probe (BTC Up/Down markets)

```bash
# Get token IDs from browser console on polymarket.com:
# fetch('https://clob.polymarket.com/markets/<conditionId>')
#   .then(r=>r.json()).then(d=>d.tokens.forEach(t=>console.log(t.token_id,'|',t.outcome)))

PYTHONPATH=. uv run python strategies/crypto_updown/latency_probe.py \
  --market <conditionId> \
  --tokens "<yesTokenId>,<noTokenId>" \
  --duration 300
```

Median lag < 500ms → directional repricing viable; ≥ 500ms → arb-only mode.

### Tests

```bash
uv run pytest          # 513 tests
uv run pytest tests/test_macro_regime.py -v   # individual module
```

---

## LLM Routing

All LLM calls go through `claude -p` (Claude Code CLI), not an API key.

```
ClaudeCodeClient.complete(system, user, model)
  └─ subprocess: echo "<prompt>" | claude -p --model <model>
       ├─ claude-haiku-4-5-20251001  — prefilter, thesis health (cheap, fast)
       └─ claude-sonnet-4-6          — analyst, challenger, auditor, thesis miner
```

**Cost model:** Claude subscription is monthly flat-rate. `DailyBudget` is set to $999 so it never blocks — tracking only.

**Per-candidate cost breakdown (equities):**

| Stage | Model | Est. cost |
|-------|-------|-----------|
| Prefilter (batch) | Haiku | ~$0.002 / batch |
| Analyst | Sonnet | ~$0.004 / candidate |
| Challenger | Sonnet | ~$0.004 / candidate |
| Auditor | Sonnet | ~$0.006 / candidate |
| Thesis health (nightly) | Haiku | ~$0.001 / position |

---

## Key Design Decisions

**Paper-only until kill-gate clears** — no real capital until ≥100 forward-paper trades with positive net PnL after simulated 0.25%/leg Revolut cost and 2% gap penalty.

**4-stage adversarial analysis** — Analyst → Challenger → Auditor prevents the model from talking itself into weak setups. The Auditor can veto both Stage 2 and Stage 3 outputs. A recommendation must survive all four stages.

**Macro regime as a first-class signal** — regime classification runs before any analysis and affects both what gets through (via tighter/looser conviction thresholds) and what the analyst is told (macro context block in every prompt).

**Supply chain graph as universe expansion** — the static supply chain graph provides a systematic way to find leaf beneficiaries of trunk re-ratings, rather than relying on the analyst's general knowledge.

**Fails open everywhere** — VIX gate, macro regime, thesis health, news providers, fundamentals enrichment: every external data dependency has a defined fallback (neutral regime, hold action, empty list) so the system never crashes on data unavailability.

**Subscription LLM** — `claude -p` subprocess avoids API key dependency; 180s timeout with graceful per-candidate skipping on slow responses.

**Geo-block handling** — CLOB REST API requires VPN in the terminal; token IDs can be obtained via browser console and passed with `--tokens`.

---

## Repository Structure

```
polymarket-bot/
├── core/
│   ├── claude_client.py        ← ClaudeCodeClient (claude -p wrapper)
│   ├── clob/                   ← Polymarket CLOB WebSocket + Gamma REST
│   ├── ledger.py               ← SQLite trade ledger + PnL
│   ├── alerts/telegram.py      ← Telegram alert formatter
│   └── execution/paper.py      ← Paper executor (slippage + fee model)
│
├── equities/
│   ├── data/
│   │   ├── fundamentals.py     ← YFinanceFundamentals (enriched snapshot)
│   │   ├── news.py             ← YFinanceNewsProvider
│   │   ├── news_tiingo.py      ← TiingoNewsProvider (optional API key)
│   │   ├── news_composite.py   ← CompositeNewsProvider (merge + dedup)
│   │   ├── prices.py           ← YFinancePriceFeed
│   │   ├── filings.py          ← SECEdgarFilings
│   │   ├── calendar.py         ← YFinanceCalendar (earnings dates)
│   │   ├── vix.py              ← VIXRegimeGate (entry blocker)
│   │   └── macro_regime.py     ← MacroRegimeGate (5-signal classifier)
│   │
│   ├── screen/
│   │   ├── event_screen.py     ← Earnings + 8-K event scanner
│   │   ├── quality_screen.py   ← Fundamental quality scorer (core sleeve)
│   │   ├── inflection_screen.py← GAAP profitability crossover screen
│   │   └── thematic_monitor.py ← Supply chain theme concentration guard
│   │
│   ├── analysis/
│   │   ├── analyst.py          ← 4-stage pipeline + signal fusion
│   │   ├── prompt.py           ← All LLM prompts (prefilter/analyst/challenger/auditor)
│   │   ├── budget.py           ← DailyBudget tracker
│   │   └── core_analyst.py     ← CoreDCAAnalyst (large-cap DCA sleeve)
│   │
│   ├── risk/
│   │   └── kernel.py           ← RiskKernel (position + sector concentration)
│   │
│   ├── killgate/
│   │   ├── tracker.py          ← ForwardPaperTracker + kill-gate
│   │   └── thesis_health.py    ← ThesisHealthChecker (nightly Haiku review)
│   │
│   └── research/
│       ├── supply_chain.py     ← SUPPLY_CHAIN graph + BottleneckScorer
│       ├── discovery_lag.py    ← DiscoveryLagCalculator
│       ├── thesis_miner.py     ← ThesisMiner (LLM → beneficiaries)
│       └── narrative_gap.py    ← NarrativeGapDetector (vocab shift)
│
├── strategies/
│   ├── llm_probability/        ← Haiku prefilter → Sonnet probability
│   ├── weather/                ← NWS forecast vs. market
│   └── crypto_updown/          ← BTC CLOB arb + repricing
│
├── orchestrator/               ← Multi-strategy allocator + risk gate
├── harness/                    ← Nightly self-improvement loop
│
├── tests/                      ← 513 unit tests (pytest)
│   ├── crypto/                 ← Polymarket strategy tests
│   ├── equities/               ← Equity module tests
│   ├── test_macro_regime.py    ← MacroRegimeGate (7 tests, fully stubbed)
│   ├── test_signal_fusion.py   ← Signal fusion tiers (5 tests)
│   ├── test_auditor_agent.py   ← 4-stage pipeline (4 tests)
│   ├── test_supply_chain.py    ← Supply chain graph (5 tests)
│   ├── test_thesis_health.py   ← Thesis health checker (3 tests)
│   └── ...                     ← 20+ additional test files
│
├── docs/plans/                 ← Implementation plans (SPEC + milestones)
├── runner.py                   ← Polymarket CLI entry point
├── runner_equities.py          ← Equities CLI entry point
└── runner_research.py          ← Weekly research CLI entry point
```

---

## License

MIT
