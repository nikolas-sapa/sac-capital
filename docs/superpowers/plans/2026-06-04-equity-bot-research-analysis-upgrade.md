# Equity Bot: Research & Analysis Full Upgrade Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the equity bot from an event-reactive system into a thesis-driven, multi-agent research and analysis engine that surfaces structurally mispriced stocks.

**Architecture:** Four phases: (1) harden existing analysis pipeline with adversarial audit + signal fusion, (2) enrich data inputs with multi-source news + richer fundamentals + VIX gating, (3) build a research intelligence layer that mines supply chain bottlenecks and narrative gaps, (4) add nightly monitoring for thesis health and thematic concentration. Each phase produces independently testable software.

**Tech Stack:** Python 3.12, pytest, yfinance, httpx, Anthropic Claude API (Haiku + Sonnet), existing `equities/` module structure.

---

## Current State vs. Target

| Layer | Current | Gap |
|---|---|---|
| Analysis | 3-stage: Haiku → Sonnet bull → Sonnet challenger | No auditor (3rd agent), hardcoded 2% sizing, no signal fusion |
| Data | yfinance headlines only | No multi-source news, no EPS trend, analyst_count unused |
| Research | EventScreen + QualityScreen | No ThesisMiner, no discovery lag, no InflectionScanner |
| Monitoring | Price-based exits only | No thesis invalidation, no thematic concentration check |

---

## File Map

### Phase 1 — Analysis Hardening
| File | Action |
|---|---|
| `equities/analysis/prompt.py` | Add `_AUDITOR_SYSTEM`, `_AUDITOR_USER`, `build_auditor_prompt()` |
| `equities/analysis/analyst.py` | Add `_audit()`, `_compute_build_action()`, inject `FundamentalsProvider`, pass analyst_count + sector to prompts |
| `equities/strategy.py` | Add `BuildAction` constants |
| `equities/risk/kernel.py` | Add sector concentration check |
| `tests/test_auditor_agent.py` | New |
| `tests/test_signal_fusion.py` | New |
| `tests/test_sector_concentration.py` | New |

### Phase 2 — Research Data Enrichment
| File | Action |
|---|---|
| `equities/data/fundamentals.py` | Add `eps_trend`, `short_interest_pct`, `peg_ratio`, `operating_margins`, `debt_to_equity`, `free_cash_flow_m` |
| `equities/data/news_tiingo.py` | New |
| `equities/data/news_composite.py` | New |
| `equities/data/vix.py` | New |
| `equities/screen/inflection_screen.py` | New |
| `runner_equities.py` | Wire VIX gate, composite news, InflectionScanner |
| `tests/test_news_composite.py` | New |
| `tests/test_vix_gate.py` | New |
| `tests/test_inflection_screen.py` | New |
| `tests/test_fundamentals_enriched.py` | New |

### Phase 3 — Research Intelligence Layer
| File | Action |
|---|---|
| `equities/research/__init__.py` | New |
| `equities/research/supply_chain.py` | New |
| `equities/research/discovery_lag.py` | New |
| `equities/research/thesis_miner.py` | New |
| `equities/research/narrative_gap.py` | New |
| `runner_research.py` | New |
| `tests/test_supply_chain.py` | New |
| `tests/test_discovery_lag.py` | New |
| `tests/test_narrative_gap.py` | New |
| `tests/test_thesis_miner.py` | New |

### Phase 4 — Monitoring Upgrades
| File | Action |
|---|---|
| `equities/killgate/thesis_health.py` | New |
| `equities/screen/thematic_monitor.py` | New |
| `runner_equities.py` | Wire nightly thesis health check, thematic monitor |
| `tests/test_thesis_health.py` | New |
| `tests/test_thematic_monitor.py` | New |

---

# Phase 1: Analysis Hardening

## Task 1: Auditor Agent + Consistency Penalty

**What:** Add a 4th LLM agent that evaluates whether the bull/bear debate was rigorous. Applies a `consistency_penalty` to final confidence when reasoning quality is low.

**Files:**
- Modify: `equities/analysis/prompt.py`
- Modify: `equities/analysis/analyst.py`
- Create: `tests/test_auditor_agent.py`

---

- [ ] **Step 1.1: Write failing test for auditor prompt builder**

```python
# tests/test_auditor_agent.py
from __future__ import annotations

from equities.analysis.prompt import build_auditor_prompt


def test_build_auditor_prompt_contains_thesis_and_objections():
    result = build_auditor_prompt(
        thesis="Strong FCF growth + AI tailwind",
        objections=["Valuation stretched", "Insider selling"],
        catalyst="Earnings beat + raised guidance",
    )
    assert "Strong FCF growth" in result
    assert "Valuation stretched" in result
    assert "Insider selling" in result
    assert "Earnings beat" in result


def test_build_auditor_prompt_with_no_objections():
    result = build_auditor_prompt(
        thesis="Clear catalyst",
        objections=[],
        catalyst="FDA approval",
    )
    assert "(none)" in result
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_auditor_agent.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_auditor_prompt'`

---

- [ ] **Step 1.2: Add auditor prompt to `equities/analysis/prompt.py`**

Add after `_CHALLENGER_USER` block, before `build_challenger_prompt`:

```python
# ---------------------------------------------------------------------------
# Stage 4 — Sonnet auditor (debate quality evaluator)
# ---------------------------------------------------------------------------

_AUDITOR_SYSTEM = """You are a debate auditor evaluating the quality of reasoning in a bull/bear equity analysis.
Do NOT decide who is right. Assess whether each side argued rigorously.

Penalize: circular logic, unbacked assertions, generic risks ("market could fall"), recency bias, no concrete data.
Reward: specific data points (revenue numbers, margin trends, dates), clear falsifiability, concrete timeframes.

Return ONLY valid JSON. No markdown, no preamble."""

_AUDITOR_USER = """Audit this bull/bear analysis.

## Catalyst
{catalyst}

## Bull thesis
{thesis}

## Bear objections
{objections_block}

Output:
{{
  "bull_rigor": <0.0-1.0>,
  "bear_rigor": <0.0-1.0>,
  "consistency_penalty": <0.0-0.25, how much to penalize final confidence for weak reasoning>,
  "fatal_flaw": <null or "one sentence describing a logical fatal flaw if found">,
  "verdict": "proceed" | "downgrade" | "reject"
}}

Verdict rules:
- "proceed": both sides argued with specifics, no fatal flaw detected
- "downgrade": one side was vague OR a genuine unaddressed concern exists
- "reject": fatal logical flaw in the bull thesis, or both sides were entirely generic"""


def build_auditor_prompt(
    thesis: str,
    objections: list[str],
    catalyst: str,
) -> str:
    objections_block = "\n".join(f"- {o}" for o in objections) or "  (none)"
    return _AUDITOR_USER.format(
        catalyst=catalyst,
        thesis=thesis,
        objections_block=objections_block,
    )
```

---

- [ ] **Step 1.3: Run prompt builder tests to verify pass**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_auditor_agent.py::test_build_auditor_prompt_contains_thesis_and_objections tests/test_auditor_agent.py::test_build_auditor_prompt_with_no_objections -v`
Expected: PASS

---

- [ ] **Step 1.4: Write failing integration test for `_audit()` method**

Append to `tests/test_auditor_agent.py`:

```python
import json

from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.strategy import Recommendation, Sleeve
from core.assets.instrument import CapTier, Instrument


_INST = Instrument("KLIC", "Kulicke and Soffa", "NASDAQ", CapTier.MID)


def _make_recommendation(confidence: float = 0.72) -> Recommendation:
    return Recommendation(
        instrument=_INST,
        sleeve=Sleeve.SWING,
        side="buy",
        entry=50.0,
        stop_loss=46.0,
        take_profit=60.0,
        size_pct=0.02,
        confidence=confidence,
        catalyst="Earnings approaching",
        thesis="Supply chain bottleneck with pricing power",
        horizon="2-3 weeks",
    )


class _StubLLMAuditProceed:
    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({
                "bull_rigor": 0.8,
                "bear_rigor": 0.4,
                "consistency_penalty": 0.05,
                "fatal_flaw": None,
                "verdict": "proceed",
            }),
            input_tokens=200,
            output_tokens=80,
        )


class _StubLLMAuditReject:
    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({
                "bull_rigor": 0.2,
                "bear_rigor": 0.9,
                "consistency_penalty": 0.25,
                "fatal_flaw": "Catalyst already fully priced in",
                "verdict": "reject",
            }),
            input_tokens=200,
            output_tokens=80,
        )


def test_auditor_proceed_applies_consistency_penalty():
    analyst = EquityAnalyst(
        llm=_StubLLMAuditProceed(),
        budget=DailyBudget(daily_limit_usd=999.0),
    )
    rec = _make_recommendation(confidence=0.72)
    result = analyst._audit(rec, objections=["Valuation stretched"])
    assert result is not None
    assert result.confidence == round(0.72 - 0.05, 3)


def test_auditor_reject_returns_none():
    analyst = EquityAnalyst(
        llm=_StubLLMAuditReject(),
        budget=DailyBudget(daily_limit_usd=999.0),
    )
    rec = _make_recommendation(confidence=0.65)
    result = analyst._audit(rec, objections=["Stock already ran 40%"])
    assert result is None
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_auditor_agent.py::test_auditor_proceed_applies_consistency_penalty -v`
Expected: FAIL with `AttributeError: 'EquityAnalyst' object has no attribute '_audit'`

---

- [ ] **Step 1.5: Add `_AUDITOR_COST` and import `build_auditor_prompt` in `analyst.py`**

Update the import block at the top of `equities/analysis/analyst.py`:

```python
from equities.analysis.prompt import (
    _ANALYST_SYSTEM,
    _AUDITOR_SYSTEM,
    _CHALLENGER_SYSTEM,
    _PREFILTER_SYSTEM,
    build_analyst_prompt,
    build_auditor_prompt,
    build_challenger_prompt,
    build_prefilter_prompt,
)
```

Add constant after `_CHALLENGER_COST = 0.008`:

```python
_AUDITOR_COST = 0.006
```

---

- [ ] **Step 1.6: Add `_audit()` method to `EquityAnalyst`**

Add after the `_challenge()` method:

```python
def _audit(
    self,
    rec: Recommendation,
    objections: list[str],
) -> Recommendation | None:
    """Run auditor pass. Applies consistency_penalty; returns None on fatal flaw."""
    if not self._budget.allow(_AUDITOR_COST):
        return rec

    user_msg = build_auditor_prompt(
        thesis=rec.thesis,
        objections=objections,
        catalyst=rec.catalyst,
    )
    try:
        resp = self._llm.complete(_AUDITOR_SYSTEM, user_msg, _SONNET)
        self._budget.record(resp.cost_usd("sonnet"))
        data = json.loads(_strip_fences(resp.content))
    except Exception:
        return rec

    if data.get("verdict") == "reject":
        return None

    consistency_penalty = float(data.get("consistency_penalty", 0.0))
    new_confidence = round(max(0.05, rec.confidence - consistency_penalty), 3)

    return Recommendation(
        instrument=rec.instrument,
        sleeve=rec.sleeve,
        side=rec.side,
        entry=rec.entry,
        stop_loss=rec.stop_loss,
        take_profit=rec.take_profit,
        size_pct=rec.size_pct,
        confidence=new_confidence,
        catalyst=rec.catalyst,
        thesis=rec.thesis,
        horizon=rec.horizon,
    )
```

---

- [ ] **Step 1.7: Update `_challenge()` to return objections alongside recommendation**

Change `_challenge()` signature and return type to `tuple[Recommendation | None, list[str]]`. The body stays the same except:
- change every `return rec` to `return rec, []`
- change `return None` to `return None, objections` (after populating `objections` from `data.get("objections", [])`)
- change the weaken `return weakened` to `return weakened, objections`
- change final `return rec` to `return rec, objections`

Also ensure `objections: list[str] = data.get("objections", [])` is extracted before the verdict checks.

---

- [ ] **Step 1.8: Update `analyse()` to chain auditor after challenger**

Replace the `analyse()` loop body:

```python
        rec = self._analyse_one(candidate)
        if rec is None:
            continue
        challenged, objections = self._challenge(rec)
        if challenged is None:
            continue
        audited = self._audit(challenged, objections)
        if audited is not None:
            results.append(audited)
```

---

- [ ] **Step 1.9: Run all auditor tests + full suite**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/ -v --tb=short`
Expected: All pass. Fix `test_challenger.py` if it calls `_challenge()` without unpacking tuple.

---

- [ ] **Step 1.10: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/analysis/prompt.py equities/analysis/analyst.py tests/test_auditor_agent.py && git commit -m "feat(analysis): add auditor agent as 4th pipeline stage with consistency penalty"
```

---

## Task 2: Signal Fusion Formula → AGGRESSIVE/GRADUAL/NIBBLE/WAIT

**What:** Replace hardcoded `size_pct=0.02` with formula-driven sizing. `composite = confidence - consistency_penalty` maps to AGGRESSIVE_BUILD (4%), GRADUAL_BUILD (2%), NIBBLE (1%), or WAIT (dropped).

**Files:**
- Modify: `equities/analysis/analyst.py`
- Create: `tests/test_signal_fusion.py`

---

- [ ] **Step 2.1: Write failing tests**

```python
# tests/test_signal_fusion.py
from __future__ import annotations

from equities.analysis.analyst import _compute_build_action


def test_high_confidence_gives_aggressive_build():
    action, size_pct = _compute_build_action(analyst_confidence=0.85, consistency_penalty=0.05)
    assert action == "AGGRESSIVE_BUILD"
    assert size_pct == 0.04


def test_medium_confidence_gives_gradual_build():
    action, size_pct = _compute_build_action(analyst_confidence=0.70, consistency_penalty=0.05)
    assert action == "GRADUAL_BUILD"
    assert size_pct == 0.02


def test_low_medium_confidence_gives_nibble():
    action, size_pct = _compute_build_action(analyst_confidence=0.55, consistency_penalty=0.05)
    assert action == "NIBBLE"
    assert size_pct == 0.01


def test_low_confidence_gives_wait():
    action, size_pct = _compute_build_action(analyst_confidence=0.50, consistency_penalty=0.10)
    assert action == "WAIT"
    assert size_pct == 0.0


def test_composite_clamped_at_zero():
    action, size_pct = _compute_build_action(analyst_confidence=0.10, consistency_penalty=0.20)
    assert action == "WAIT"
    assert size_pct == 0.0
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_signal_fusion.py -v`
Expected: FAIL with `ImportError: cannot import name '_compute_build_action'`

---

- [ ] **Step 2.2: Add `_compute_build_action()` to `equities/analysis/analyst.py`**

Add as a module-level function before `_strip_fences`:

```python
def _compute_build_action(
    analyst_confidence: float,
    consistency_penalty: float,
) -> tuple[str, float]:
    """Map composite score to build action and size_pct.

    composite = analyst_confidence - consistency_penalty, clamped [0, 1].
    AGGRESSIVE_BUILD >= 0.75 -> 4%
    GRADUAL_BUILD    >= 0.60 -> 2%
    NIBBLE           >= 0.45 -> 1%
    WAIT             <  0.45 -> 0% (skip)
    """
    composite = max(0.0, min(1.0, analyst_confidence - consistency_penalty))
    if composite >= 0.75:
        return "AGGRESSIVE_BUILD", 0.04
    if composite >= 0.60:
        return "GRADUAL_BUILD", 0.02
    if composite >= 0.45:
        return "NIBBLE", 0.01
    return "WAIT", 0.0
```

---

- [ ] **Step 2.3: Wire `_compute_build_action` into `analyse()`**

After `audited = self._audit(challenged, objections)` and the None check, replace `results.append(audited)` with:

```python
        _action, size_pct = _compute_build_action(
            analyst_confidence=audited.confidence,
            consistency_penalty=0.0,  # already applied by auditor
        )
        if size_pct == 0.0:
            continue  # WAIT — skip

        final = Recommendation(
            instrument=audited.instrument,
            sleeve=audited.sleeve,
            side=audited.side,
            entry=audited.entry,
            stop_loss=audited.stop_loss,
            take_profit=audited.take_profit,
            size_pct=size_pct,
            confidence=audited.confidence,
            catalyst=audited.catalyst,
            thesis=audited.thesis,
            horizon=audited.horizon,
        )
        results.append(final)
```

---

- [ ] **Step 2.4: Run tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_signal_fusion.py tests/ -v --tb=short`
Expected: All pass.

---

- [ ] **Step 2.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/analysis/analyst.py tests/test_signal_fusion.py && git commit -m "feat(analysis): signal fusion formula AGGRESSIVE/GRADUAL/NIBBLE/WAIT replaces hardcoded 2%"
```

---

## Task 3: Analyst Context Enrichment (analyst_count + sector in prompts)

**What:** `FundamentalsSnapshot` has `analyst_count` and `sector` but neither reaches the LLM. Inject both into Haiku prefilter and Sonnet analyst prompts. Under-covered stocks get a +1 score bonus from Haiku.

**Files:**
- Modify: `equities/analysis/prompt.py`
- Modify: `equities/analysis/analyst.py`
- Modify: `runner_equities.py`

---

- [ ] **Step 3.1: Update `_PREFILTER_USER` to mention analyst coverage**

In `equities/analysis/prompt.py`, replace `_PREFILTER_USER`:

```python
_PREFILTER_USER = """Score each of these equity catalysts. Under-followed stocks (< 5 sell-side analysts) deserve a coverage bonus of +1 to your score — the market is less informed.

{candidates_block}

Return JSON rankings."""
```

Update `build_prefilter_prompt()` to accept and include analyst_counts:

```python
def build_prefilter_prompt(
    candidates: list[CandidateEvent],
    analyst_counts: dict[str, int] | None = None,
) -> str:
    lines = []
    for c in candidates:
        coverage = ""
        if analyst_counts:
            n = analyst_counts.get(c.instrument.ticker, 0)
            coverage = f" | analysts={n}"
        lines.append(
            f"- {c.instrument.ticker} ({c.instrument.cap_tier.value} cap): "
            f"{c.event_type.value} | {c.evidence}{coverage}"
        )
    return _PREFILTER_USER.format(candidates_block="\n".join(lines))
```

---

- [ ] **Step 3.2: Update `_ANALYST_USER` and `build_analyst_prompt()` to include sector and analyst_count**

Replace `_ANALYST_USER` in `equities/analysis/prompt.py`:

```python
_ANALYST_USER = """Analyze this equity catalyst.

## Candidate
Ticker: {ticker}
Sector: {sector}
Analyst coverage: {analyst_count} sell-side analysts (< 5 = under-followed = higher opportunity)
Event: {event_type} — {evidence}
Current price: ${current_price:.2f}
Cap tier: {cap_tier}

## Recent news (last 8 headlines)
{news_block}

## Recent SEC filings (last 90 days)
{filings_block}

## Task
If this setup is already priced in OR has no clear thesis, output:
{{"action": "reject", "reason": "one sentence"}}

Otherwise output:
{{
  "action": "buy",
  "entry": <limit price as float>,
  "stop_loss": <stop price where thesis is broken>,
  "take_profit": <target where re-rating completes>,
  "confidence": <0.0-1.0>,
  "horizon": "<e.g. 1-2 weeks>",
  "catalyst": "<one sentence: what specific event drives this>",
  "thesis": "<2-3 sentences: what the market is missing>"
}}"""
```

Update `build_analyst_prompt()`:

```python
def build_analyst_prompt(
    candidate: CandidateEvent,
    current_price: float,
    news: list[str],
    filings: list[str],
    sector: str = "",
    analyst_count: int = 0,
) -> str:
    news_block = "\n".join(f"- {h}" for h in news[:8]) or "  (none)"
    filings_block = "\n".join(f"- {f}" for f in filings[:5]) or "  (none)"
    return _ANALYST_USER.format(
        ticker=candidate.instrument.ticker,
        sector=sector or "Unknown",
        analyst_count=analyst_count,
        event_type=candidate.event_type.value,
        evidence=candidate.evidence,
        current_price=current_price,
        cap_tier=candidate.instrument.cap_tier.value,
        news_block=news_block,
        filings_block=filings_block,
    )
```

---

- [ ] **Step 3.3: Add `FundamentalsProvider` injection to `EquityAnalyst`**

In `equities/analysis/analyst.py`, add import:

```python
from equities.data.fundamentals import FundamentalsProvider
```

Add `fundamentals: FundamentalsProvider | None = None` parameter to `__init__` and store as `self._fundamentals = fundamentals`.

Update `_analyse_one()` to fetch sector and analyst_count before calling `build_analyst_prompt`:

```python
    sector = ""
    analyst_count = 0
    if self._fundamentals:
        try:
            snap = self._fundamentals.fetch(candidate.instrument.ticker)
            sector = snap.sector
            analyst_count = snap.analyst_count
        except Exception:
            pass

    user_msg = build_analyst_prompt(
        candidate=candidate,
        current_price=price,
        news=headlines,
        filings=filing_lines,
        sector=sector,
        analyst_count=analyst_count,
    )
```

---

- [ ] **Step 3.4: Update `runner_equities.py` to pass `fundamentals_provider` to `EquityAnalyst`**

```python
    analyst = EquityAnalyst(
        llm=ClaudeCodeClient(),
        prices=prices,
        news=news,
        filings=filings_summary,
        fundamentals=fundamentals_provider,   # add this
        budget=budget,
        max_candidates=5,
    )
```

---

- [ ] **Step 3.5: Run full test suite**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/ -v --tb=short`
Expected: All pass.

---

- [ ] **Step 3.6: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/analysis/prompt.py equities/analysis/analyst.py runner_equities.py && git commit -m "feat(analysis): inject analyst_count + sector into Haiku prefilter and Sonnet analyst prompts"
```

---

## Task 4: Sector Concentration Check in RiskKernel

**What:** Add `max_sector_pct` fuse (default 35%) so the portfolio cannot accidentally stack 60% semiconductors.

**Files:**
- Modify: `equities/risk/kernel.py`
- Create: `tests/test_sector_concentration.py`

---

- [ ] **Step 4.1: Write failing tests**

```python
# tests/test_sector_concentration.py
from __future__ import annotations

from equities.risk.kernel import RiskKernel
from equities.strategy import Recommendation, Sleeve
from core.assets.instrument import CapTier, Instrument


def _rec(ticker: str, entry: float = 100.0) -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.MID),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=entry * 0.92,
        take_profit=entry * 1.20,
        size_pct=0.02,
        confidence=0.70,
        catalyst="test",
        thesis="test",
        horizon="2w",
    )


def test_sector_concentration_blocks_entry():
    kernel = RiskKernel(capital=100_000, max_positions=10, max_sector_pct=0.25)
    open_positions = [
        {"ticker": "KLIC", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "ONTO", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "AMKR", "sleeve": "swing", "shares": 50,  "entry_price": 100.0, "sector": "Semiconductors"},
    ]
    # Existing semiconductors = $25k = 25% — adding one more would push over
    result = kernel.approve(
        _rec("LRCX"),
        open_positions,
        sector_lookup={"LRCX": "Semiconductors"},
    )
    assert not result.approved
    assert "sector_concentration" in result.rejection_reason


def test_different_sector_not_blocked():
    kernel = RiskKernel(capital=100_000, max_positions=10, max_sector_pct=0.25)
    open_positions = [
        {"ticker": "KLIC", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "ONTO", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "AMKR", "sleeve": "swing", "shares": 50,  "entry_price": 100.0, "sector": "Semiconductors"},
    ]
    result = kernel.approve(
        _rec("CRWD"),
        open_positions,
        sector_lookup={"CRWD": "Technology"},
    )
    assert result.approved
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_sector_concentration.py -v`
Expected: FAIL

---

- [ ] **Step 4.2: Add `max_sector_pct` to `RiskKernel.__init__`**

Add `max_sector_pct: float = 0.35` parameter and `self.max_sector_pct = max_sector_pct` assignment.

---

- [ ] **Step 4.3: Add `sector_lookup` parameter to `RiskKernel.approve()` and sector check**

Update `approve()` signature:

```python
def approve(
    self,
    recommendation: Any,
    open_positions: list[dict[str, Any]],
    today_realized_loss: float = 0.0,
    current_equity: float | None = None,
    sector_lookup: dict[str, str] | None = None,
) -> SizedRecommendation:
```

Add sector check after the per-name concentration check block:

```python
        # --- Sector concentration cap ---
        if sector_lookup is not None:
            new_sector = sector_lookup.get(ticker, "")
            if new_sector:
                sector_exposure = sum(
                    p.get("shares", 0) * p.get("entry_price", 0)
                    for p in swing_open
                    if p.get("sector", "") == new_sector
                )
                if sector_exposure / self.capital >= self.max_sector_pct:
                    return SizedRecommendation(
                        recommendation, 0.0, False,
                        f"sector_concentration_{new_sector}_at_{self.max_sector_pct:.0%}_limit",
                    )
```

---

- [ ] **Step 4.4: Run tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_sector_concentration.py tests/ -v --tb=short`
Expected: All pass.

---

- [ ] **Step 4.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/risk/kernel.py tests/test_sector_concentration.py && git commit -m "feat(risk): sector concentration fuse added to RiskKernel (default 35% per sector)"
```

---

# Phase 2: Research Data Enrichment

## Task 5: Enrich FundamentalsSnapshot

**What:** Add `eps_trend`, `short_interest_pct`, `peg_ratio`, `operating_margins`, `debt_to_equity`, `free_cash_flow_m` to `FundamentalsSnapshot`. Used by InflectionScanner (Task 8) and NarrativeGapDetector.

**Files:**
- Modify: `equities/data/fundamentals.py`
- Create: `tests/test_fundamentals_enriched.py`

---

- [ ] **Step 5.1: Write failing test**

```python
# tests/test_fundamentals_enriched.py
from __future__ import annotations

from equities.data.fundamentals import FundamentalsSnapshot


def test_snapshot_has_enriched_fields():
    snap = FundamentalsSnapshot(
        ticker="AMD",
        market_cap_m=250_000.0,
        trailing_pe=35.0,
        forward_pe=28.0,
        gross_margins=0.53,
        revenue_growth=0.17,
        sector="Semiconductors",
        analyst_count=42,
        eps_trend=[-0.40, -0.25, -0.10, 0.05],
        short_interest_pct=1.8,
        peg_ratio=1.4,
        operating_margins=0.22,
        debt_to_equity=0.35,
        free_cash_flow_m=1_200.0,
    )
    assert snap.eps_trend == [-0.40, -0.25, -0.10, 0.05]
    assert snap.short_interest_pct == 1.8
    assert snap.peg_ratio == 1.4
    assert snap.operating_margins == 0.22


def test_enriched_fields_default_safely():
    snap = FundamentalsSnapshot(
        ticker="TEST",
        market_cap_m=None,
        trailing_pe=None,
        forward_pe=None,
        gross_margins=None,
        revenue_growth=None,
        sector="",
        analyst_count=0,
    )
    assert snap.eps_trend == []
    assert snap.short_interest_pct is None
    assert snap.peg_ratio is None
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_fundamentals_enriched.py -v`
Expected: FAIL

---

- [ ] **Step 5.2: Enrich `FundamentalsSnapshot` dataclass**

Replace the `FundamentalsSnapshot` dataclass in `equities/data/fundamentals.py`:

```python
@dataclass
class FundamentalsSnapshot:
    """Key fundamental metrics for a single ticker, fetched at a point in time."""

    ticker: str
    market_cap_m: float | None
    trailing_pe: float | None
    forward_pe: float | None
    gross_margins: float | None
    revenue_growth: float | None
    sector: str
    analyst_count: int
    # Enriched fields
    eps_trend: list[float] | None = None       # last 4 quarterly EPS, oldest first
    short_interest_pct: float | None = None    # short interest as % of float
    peg_ratio: float | None = None
    operating_margins: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow_m: float | None = None      # free cash flow in $M

    def __post_init__(self) -> None:
        if self.eps_trend is None:
            self.eps_trend = []
```

Note: Remove `frozen=True` to allow `__post_init__` mutation, or keep frozen and use `object.__setattr__`.

If keeping `frozen=True`:
```python
    def __post_init__(self) -> None:
        if self.eps_trend is None:
            object.__setattr__(self, "eps_trend", [])
```

---

- [ ] **Step 5.3: Update `YFinanceFundamentals.fetch()` to populate new fields**

Add new fields to the return value:

```python
        cap_raw = info.get("marketCap")
        fcf_raw = info.get("freeCashflow")

        eps_trend: list[float] = []
        try:
            eh = t.earnings_history
            if eh is not None and not eh.empty and "epsActual" in eh.columns:
                recent = eh.sort_index().tail(4)
                eps_trend = [float(v) for v in recent["epsActual"].fillna(0).tolist()]
        except Exception:
            eps_trend = []

        return FundamentalsSnapshot(
            ticker=ticker,
            market_cap_m=cap_raw / 1e6 if cap_raw else None,
            trailing_pe=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            gross_margins=info.get("grossMargins"),
            revenue_growth=info.get("revenueGrowth"),
            sector=info.get("sector", ""),
            analyst_count=info.get("numberOfAnalystOpinions", 0) or 0,
            eps_trend=eps_trend,
            short_interest_pct=info.get("shortPercentOfFloat"),
            peg_ratio=info.get("pegRatio"),
            operating_margins=info.get("operatingMargins"),
            debt_to_equity=info.get("debtToEquity"),
            free_cash_flow_m=fcf_raw / 1e6 if fcf_raw else None,
        )
```

---

- [ ] **Step 5.4: Run tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_fundamentals_enriched.py tests/ -v --tb=short`
Expected: All pass.

---

- [ ] **Step 5.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/data/fundamentals.py tests/test_fundamentals_enriched.py && git commit -m "feat(data): enrich FundamentalsSnapshot with eps_trend, short_interest_pct, peg_ratio, operating_margins, fcf"
```

---

## Task 6: Multi-Source News Aggregator (Tiingo + yfinance)

**Files:**
- Create: `equities/data/news_tiingo.py`
- Create: `equities/data/news_composite.py`
- Modify: `runner_equities.py`
- Create: `tests/test_news_composite.py`

---

- [ ] **Step 6.1: Write failing tests**

```python
# tests/test_news_composite.py
from __future__ import annotations

from equities.data.news_composite import CompositeNewsProvider


class _StubProvider:
    def __init__(self, items: list[str]) -> None:
        self._items = items

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        return self._items[:limit]


def test_composite_merges_and_deduplicates():
    p1 = _StubProvider(["Apple beats estimates", "Apple raises guidance"])
    p2 = _StubProvider(["Apple beats estimates", "Apple new product launch"])
    comp = CompositeNewsProvider([p1, p2])
    result = comp.headlines("AAPL", limit=10)
    assert len(result) == 3
    assert "Apple beats estimates" in result
    assert "Apple new product launch" in result


def test_composite_respects_limit():
    p1 = _StubProvider([f"headline_{i}" for i in range(10)])
    p2 = _StubProvider([f"other_{i}" for i in range(10)])
    comp = CompositeNewsProvider([p1, p2])
    assert len(comp.headlines("AAPL", limit=5)) == 5


def test_composite_handles_empty_provider():
    p1 = _StubProvider([])
    p2 = _StubProvider(["Real news"])
    comp = CompositeNewsProvider([p1, p2])
    assert comp.headlines("AAPL", limit=10) == ["Real news"]
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_news_composite.py -v`
Expected: FAIL

---

- [ ] **Step 6.2: Create `equities/data/news_tiingo.py`**

```python
"""Tiingo news provider — free tier requires TIINGO_API_KEY env var."""
from __future__ import annotations

import os


class TiingoNewsProvider:
    """Fetch news from Tiingo API. Falls back to empty list if key absent or request fails."""

    _BASE = "https://api.tiingo.com/tiingo/news"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or os.getenv("TIINGO_API_KEY", "")

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        if not self._key:
            return []
        try:
            import httpx
            resp = httpx.get(
                self._BASE,
                params={"tickers": ticker, "limit": limit, "token": self._key},
                headers={"Content-Type": "application/json"},
                timeout=8,
            )
            resp.raise_for_status()
            results: list[str] = []
            for a in resp.json()[:limit]:
                title = a.get("title", "")
                desc = (a.get("description") or "")[:120].strip()
                if title:
                    results.append(f"{title} — {desc}" if desc else title)
            return results
        except Exception:
            return []
```

---

- [ ] **Step 6.3: Create `equities/data/news_composite.py`**

```python
"""Composite news provider — aggregates multiple providers and deduplicates."""
from __future__ import annotations

from typing import Protocol


class NewsProvider(Protocol):
    def headlines(self, ticker: str, limit: int = 15) -> list[str]: ...


class CompositeNewsProvider:
    """Aggregate headlines from multiple providers, deduplicating by exact match."""

    def __init__(self, providers: list[NewsProvider]) -> None:
        self._providers = providers

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for provider in self._providers:
            try:
                items = provider.headlines(ticker, limit=limit)
            except Exception:
                items = []
            for item in items:
                normalized = item.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    merged.append(normalized)
                if len(merged) >= limit:
                    break
            if len(merged) >= limit:
                break
        return merged[:limit]
```

---

- [ ] **Step 6.4: Run news tests and update `runner_equities.py`**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_news_composite.py -v`
Expected: All PASS

In `run_once()` in `runner_equities.py`, replace `news = YFinanceNewsProvider()`:

```python
from equities.data.news_tiingo import TiingoNewsProvider
from equities.data.news_composite import CompositeNewsProvider

    news = CompositeNewsProvider([
        YFinanceNewsProvider(),
        TiingoNewsProvider(),   # no-op if TIINGO_API_KEY absent
    ])
```

---

- [ ] **Step 6.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/data/news_tiingo.py equities/data/news_composite.py runner_equities.py tests/test_news_composite.py && git commit -m "feat(data): Tiingo news provider + CompositeNewsProvider with deduplication"
```

---

## Task 7: VIX Regime Gate

**What:** Block new swing entries when VIX > 30. Fetches live VIX from yfinance (^VIX). Fails open if VIX unavailable.

**Files:**
- Create: `equities/data/vix.py`
- Modify: `runner_equities.py`
- Create: `tests/test_vix_gate.py`

---

- [ ] **Step 7.1: Write failing tests**

```python
# tests/test_vix_gate.py
from __future__ import annotations

from equities.data.vix import VIXRegimeGate


class _StubVIX(VIXRegimeGate):
    def __init__(self, val: float | None, threshold: float = 30.0) -> None:
        super().__init__(threshold=threshold)
        self._val = val

    def current_vix(self) -> float | None:
        return self._val


def test_low_vix_allows_entries():
    gate = _StubVIX(18.5)
    allowed, vix = gate.allow_new_entries()
    assert allowed is True
    assert vix == 18.5


def test_high_vix_blocks_entries():
    gate = _StubVIX(35.2)
    allowed, vix = gate.allow_new_entries()
    assert allowed is False
    assert vix == 35.2


def test_none_vix_fails_open():
    gate = _StubVIX(None)
    allowed, vix = gate.allow_new_entries()
    assert allowed is True
    assert vix is None


def test_custom_threshold():
    gate = _StubVIX(25.0, threshold=20.0)
    allowed, _ = gate.allow_new_entries()
    assert allowed is False
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_vix_gate.py -v`
Expected: FAIL

---

- [ ] **Step 7.2: Create `equities/data/vix.py`**

```python
"""VIX regime gate — blocks new swing entries during high-fear market regimes."""
from __future__ import annotations


class VIXRegimeGate:
    """Fetch current VIX and determine whether new swing entries are permitted.

    Fails open (returns True) if VIX data is unavailable.
    """

    def __init__(self, threshold: float = 30.0) -> None:
        self._threshold = threshold

    def current_vix(self) -> float | None:
        try:
            import yfinance as yf
            data = yf.Ticker("^VIX").history(period="2d")
            if data.empty:
                return None
            return float(data["Close"].iloc[-1])
        except Exception:
            return None

    def allow_new_entries(self) -> tuple[bool, float | None]:
        """Return (allowed, current_vix). Fails open when vix is None."""
        vix = self.current_vix()
        if vix is None:
            return True, None
        return vix < self._threshold, vix
```

---

- [ ] **Step 7.3: Run VIX tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_vix_gate.py -v`
Expected: All PASS

---

- [ ] **Step 7.4: Wire VIX gate into `runner_equities.py`**

Add after the scan summary alert in `run_once()`, before the analyst stage:

```python
    from equities.data.vix import VIXRegimeGate
    vix_gate = VIXRegimeGate(threshold=30.0)
    entries_allowed, current_vix = vix_gate.allow_new_entries()
    if current_vix is not None:
        print(f"\nVIX: {current_vix:.1f} | entries_allowed={entries_allowed}")
    if not entries_allowed:
        print(f"VIX={current_vix:.1f} > 30 — blocking new entries. Running mark-to-market only.")
        if alerts is not None:
            await alerts.send(f"VIX={current_vix:.1f} — new entries blocked today.")
        equity_ledger.close()
        fp_tracker.close()
        return
```

---

- [ ] **Step 7.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/data/vix.py runner_equities.py tests/test_vix_gate.py && git commit -m "feat(risk): VIX regime gate blocks new swing entries when VIX > 30"
```

---

## Task 8: Inflection Scanner

**What:** Find stocks 1–2 quarters from first GAAP profitability. Uses `eps_trend` from enriched `FundamentalsSnapshot`. These are coiled springs: index inclusion, short cover, multiple expansion.

**Files:**
- Create: `equities/screen/inflection_screen.py`
- Create: `tests/test_inflection_screen.py`
- Modify: `runner_equities.py`

---

- [ ] **Step 8.1: Write failing tests**

```python
# tests/test_inflection_screen.py
from __future__ import annotations

from equities.screen.inflection_screen import InflectionScanner, InflectionCandidate
from equities.data.fundamentals import FundamentalsSnapshot
from core.assets.instrument import CapTier, Instrument


def _inst(ticker: str) -> Instrument:
    return Instrument(ticker, ticker, "NASDAQ", CapTier.MID)


def _snap(ticker: str, eps: list[float], rev: float = 0.30) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        ticker=ticker,
        market_cap_m=2_000.0,
        trailing_pe=None,
        forward_pe=None,
        gross_margins=0.60,
        revenue_growth=rev,
        sector="Technology",
        analyst_count=6,
        eps_trend=eps,
        short_interest_pct=12.0,
    )


class _StubFundamentals:
    def __init__(self, snaps: dict) -> None:
        self._snaps = snaps

    def fetch(self, ticker: str) -> FundamentalsSnapshot:
        return self._snaps[ticker]


def test_improving_eps_near_zero_is_flagged():
    scanner = InflectionScanner(_StubFundamentals({"AFRM": _snap("AFRM", [-0.45, -0.30, -0.15, -0.05])}))
    results = scanner.scan([_inst("AFRM")])
    assert len(results) == 1
    assert results[0].ticker == "AFRM"
    assert results[0].quarters_to_profit <= 2


def test_already_profitable_not_flagged():
    scanner = InflectionScanner(_StubFundamentals({"META": _snap("META", [1.0, 1.5, 2.0, 2.5])}))
    assert scanner.scan([_inst("META")]) == []


def test_deteriorating_eps_not_flagged():
    scanner = InflectionScanner(_StubFundamentals({"PTON": _snap("PTON", [-0.05, -0.15, -0.30, -0.50])}))
    assert scanner.scan([_inst("PTON")]) == []


def test_no_eps_data_skipped():
    scanner = InflectionScanner(_StubFundamentals({"X": _snap("X", [])}))
    assert scanner.scan([_inst("X")]) == []
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_inflection_screen.py -v`
Expected: FAIL

---

- [ ] **Step 8.2: Create `equities/screen/inflection_screen.py`**

```python
"""Inflection scanner — finds companies 1-2 quarters from first GAAP profitability."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.assets.instrument import Instrument
from equities.data.fundamentals import FundamentalsSnapshot


class FundamentalsProvider(Protocol):
    def fetch(self, ticker: str) -> FundamentalsSnapshot: ...


@dataclass(frozen=True)
class InflectionCandidate:
    ticker: str
    instrument: Instrument
    eps_trend: list[float]
    quarters_to_profit: int
    revenue_growth: float
    short_interest_pct: float | None
    evidence: str


class InflectionScanner:
    """Scan for companies approaching GAAP profitability.

    All must pass:
    - 3+ consecutive quarters of EPS improvement
    - Last quarter still negative
    - Last quarter EPS > max_eps_loss (close to zero)
    - Revenue growth >= min_revenue_growth
    """

    def __init__(
        self,
        fundamentals: FundamentalsProvider,
        max_eps_loss: float = -0.20,
        min_revenue_growth: float = 0.10,
    ) -> None:
        self._fundamentals = fundamentals
        self._max_eps_loss = max_eps_loss
        self._min_revenue_growth = min_revenue_growth

    def scan(self, universe: list[Instrument]) -> list[InflectionCandidate]:
        results: list[InflectionCandidate] = []
        for inst in universe:
            try:
                snap = self._fundamentals.fetch(inst.ticker)
            except Exception:
                continue
            c = self._evaluate(inst, snap)
            if c is not None:
                results.append(c)
        results.sort(key=lambda c: c.eps_trend[-1], reverse=True)
        return results

    def _evaluate(self, inst: Instrument, snap: FundamentalsSnapshot) -> InflectionCandidate | None:
        eps = snap.eps_trend or []
        if len(eps) < 3:
            return None
        if not all(eps[i] > eps[i - 1] for i in range(1, len(eps))):
            return None
        last = eps[-1]
        if last >= 0:
            return None
        if last < self._max_eps_loss:
            return None
        rev_g = snap.revenue_growth or 0.0
        if rev_g < self._min_revenue_growth:
            return None
        avg_improvement = (eps[-1] - eps[0]) / (len(eps) - 1)
        quarters_to_profit = max(1, round(-last / avg_improvement)) if avg_improvement > 0 else 2
        si = snap.short_interest_pct
        evidence = (
            f"eps={[round(e, 2) for e in eps]} "
            f"rev={rev_g:+.0%}"
            + (f" si={si:.1f}%" if si else "")
        )
        return InflectionCandidate(
            ticker=inst.ticker,
            instrument=inst,
            eps_trend=eps,
            quarters_to_profit=min(quarters_to_profit, 2),
            revenue_growth=rev_g,
            short_interest_pct=si,
            evidence=evidence,
        )
```

---

- [ ] **Step 8.3: Run inflection tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_inflection_screen.py -v`
Expected: All PASS

---

- [ ] **Step 8.4: Wire InflectionScanner into `runner_equities.py`**

After the quality screen section in `run_once()`:

```python
    from equities.screen.inflection_screen import InflectionScanner
    inflection_screen = InflectionScanner(fundamentals_provider)
    inflection_candidates = inflection_screen.scan(swing_universe)
    print(f"\n=== Inflection candidates: {len(inflection_candidates)} ===")
    for c in inflection_candidates:
        print(f"  [{c.ticker}] ~{c.quarters_to_profit}q to profit | {c.evidence}")
```

---

- [ ] **Step 8.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/screen/inflection_screen.py runner_equities.py tests/test_inflection_screen.py && git commit -m "feat(screen): InflectionScanner for profitability crossover candidates"
```

---

# Phase 3: Research Intelligence Layer

## Task 9: Supply Chain Graph + Bottleneck Scorer + Discovery Lag

**What:** Static graph mapping trunk companies (NVDA, AVGO, LLY, etc.) to their leaf suppliers. Score each leaf by bottleneck strength. Compute discovery lag (trunk 12m return − leaf 12m return) to surface unpriced supply chain plays.

**Files:**
- Create: `equities/research/__init__.py`
- Create: `equities/research/supply_chain.py`
- Create: `equities/research/discovery_lag.py`
- Create: `tests/test_supply_chain.py`
- Create: `tests/test_discovery_lag.py`

---

- [ ] **Step 9.1: Write failing tests**

```python
# tests/test_supply_chain.py
from __future__ import annotations

from equities.research.supply_chain import (
    SUPPLY_CHAIN,
    BottleneckScorer,
    get_leaves_for_trunk,
    get_trunks_for_leaf,
)


def test_nvda_has_expected_leaves():
    leaves = get_leaves_for_trunk("NVDA")
    assert "MU" in leaves
    assert "COHR" in leaves
    assert "AMKR" in leaves


def test_unknown_trunk_returns_empty():
    assert get_leaves_for_trunk("FAKECO") == []


def test_leaf_trunks_lookup():
    trunks = get_trunks_for_leaf("MU")
    assert "NVDA" in trunks


def test_bottleneck_score_range():
    scorer = BottleneckScorer()
    score = scorer.score("MU", trunk="NVDA")
    assert 0.0 <= score <= 1.0


def test_asml_monopoly_scores_near_one():
    scorer = BottleneckScorer()
    assert scorer.score("ASML", trunk="TSM") > 0.8
```

```python
# tests/test_discovery_lag.py
from __future__ import annotations

import pytest
from equities.research.discovery_lag import DiscoveryLagCalculator


class _StubLag(DiscoveryLagCalculator):
    def _fetch_12m_return(self, ticker: str) -> float | None:
        returns = {"NVDA": 150.0, "COHR": 40.0, "MU": 80.0}
        return returns.get(ticker)


def test_lag_is_trunk_minus_leaf():
    calc = _StubLag()
    assert calc.compute("NVDA", "COHR") == pytest.approx(110.0)


def test_missing_ticker_returns_zero():
    calc = _StubLag()
    assert calc.compute("NVDA", "UNKN") == 0.0
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_supply_chain.py tests/test_discovery_lag.py -v`
Expected: FAIL

---

- [ ] **Step 9.2: Create `equities/research/__init__.py`**

```python
"""Research intelligence layer — supply chain mapping, discovery lag, thesis mining."""
```

---

- [ ] **Step 9.3: Create `equities/research/supply_chain.py`**

```python
"""Static supply chain graph mapping trunk companies to leaf suppliers."""
from __future__ import annotations

from dataclasses import dataclass


SUPPLY_CHAIN: dict[str, list[str]] = {
    "NVDA": ["MU", "COHR", "AMKR", "ONTO", "KLIC", "FN", "APH", "ENTG", "LRCX", "KLAC", "VRT", "MPWR", "AMAT", "CLS"],
    "AMD":  ["MU", "AMKR", "COHR", "LRCX", "AMAT"],
    "AVGO": ["AMKR", "COHR", "MU", "MRVL"],
    "TSM":  ["ASML", "LRCX", "KLAC", "AMAT", "ENTG"],
    "LLY":  ["DOCS", "GEHC", "TEM", "HIMS"],
    "MSFT": ["NOW", "CRM", "CRWD", "DDOG"],
    "GOOGL":["VRT", "ETN", "GEV", "CEG", "PWR"],
    "AMZN": ["VRT", "ETN", "GEV", "CEG"],
}

_BOTTLENECK_META: dict[str, dict[str, float]] = {
    "MU":   {"market_share": 0.25, "switching_cost": 0.90, "lead_time_years": 3.0},
    "COHR": {"market_share": 0.30, "switching_cost": 0.80, "lead_time_years": 2.0},
    "AMKR": {"market_share": 0.15, "switching_cost": 0.70, "lead_time_years": 2.5},
    "ASML": {"market_share": 0.90, "switching_cost": 1.00, "lead_time_years": 5.0},
    "LRCX": {"market_share": 0.45, "switching_cost": 0.85, "lead_time_years": 3.0},
    "KLAC": {"market_share": 0.50, "switching_cost": 0.85, "lead_time_years": 3.0},
    "ENTG": {"market_share": 0.35, "switching_cost": 0.75, "lead_time_years": 2.0},
    "VRT":  {"market_share": 0.25, "switching_cost": 0.60, "lead_time_years": 1.5},
    "ONTO": {"market_share": 0.20, "switching_cost": 0.70, "lead_time_years": 2.0},
    "KLIC": {"market_share": 0.25, "switching_cost": 0.65, "lead_time_years": 1.5},
    "FN":   {"market_share": 0.30, "switching_cost": 0.70, "lead_time_years": 1.5},
    "APH":  {"market_share": 0.10, "switching_cost": 0.50, "lead_time_years": 1.0},
    "AMAT": {"market_share": 0.20, "switching_cost": 0.80, "lead_time_years": 3.0},
    "CLS":  {"market_share": 0.15, "switching_cost": 0.50, "lead_time_years": 1.0},
    "DOCS": {"market_share": 0.20, "switching_cost": 0.60, "lead_time_years": 1.0},
    "GEHC": {"market_share": 0.15, "switching_cost": 0.70, "lead_time_years": 2.0},
    "TEM":  {"market_share": 0.05, "switching_cost": 0.50, "lead_time_years": 1.0},
    "HIMS": {"market_share": 0.05, "switching_cost": 0.30, "lead_time_years": 0.5},
    "NOW":  {"market_share": 0.15, "switching_cost": 0.85, "lead_time_years": 2.0},
    "CRWD": {"market_share": 0.20, "switching_cost": 0.90, "lead_time_years": 2.0},
    "DDOG": {"market_share": 0.12, "switching_cost": 0.75, "lead_time_years": 1.5},
    "ETN":  {"market_share": 0.15, "switching_cost": 0.60, "lead_time_years": 2.0},
    "GEV":  {"market_share": 0.10, "switching_cost": 0.70, "lead_time_years": 3.0},
    "CEG":  {"market_share": 0.08, "switching_cost": 0.80, "lead_time_years": 5.0},
    "PWR":  {"market_share": 0.10, "switching_cost": 0.50, "lead_time_years": 1.0},
    "MPWR": {"market_share": 0.10, "switching_cost": 0.70, "lead_time_years": 1.5},
    "MRVL": {"market_share": 0.12, "switching_cost": 0.75, "lead_time_years": 2.0},
    "CRM":  {"market_share": 0.20, "switching_cost": 0.80, "lead_time_years": 2.0},
}

_DEFAULT_META = {"market_share": 0.05, "switching_cost": 0.40, "lead_time_years": 1.0}


@dataclass(frozen=True)
class SupplyChainNode:
    ticker: str
    trunk: str
    bottleneck_score: float
    discovery_lag_pct: float


def get_leaves_for_trunk(trunk: str) -> list[str]:
    return SUPPLY_CHAIN.get(trunk, [])


def get_trunks_for_leaf(leaf: str) -> list[str]:
    return [t for t, leaves in SUPPLY_CHAIN.items() if leaf in leaves]


class BottleneckScorer:
    """Score a leaf supplier's bottleneck strength (0.0-1.0).

    Score = market_share*0.35 + switching_cost*0.45 + lead_time_factor*0.20
    """

    def score(self, leaf: str, trunk: str) -> float:  # noqa: ARG002
        meta = _BOTTLENECK_META.get(leaf, _DEFAULT_META)
        raw = (
            meta["market_share"] * 0.35
            + meta["switching_cost"] * 0.45
            + min(1.0, meta["lead_time_years"] / 5.0) * 0.20
        )
        return round(min(1.0, raw), 4)
```

---

- [ ] **Step 9.4: Create `equities/research/discovery_lag.py`**

```python
"""Discovery lag — measures how far a leaf supplier's stock lags the trunk."""
from __future__ import annotations


class DiscoveryLagCalculator:
    """Compute discovery_lag = trunk_12m_return_pct - leaf_12m_return_pct."""

    def compute(self, trunk: str, leaf: str) -> float:
        t = self._fetch_12m_return(trunk)
        l = self._fetch_12m_return(leaf)
        if t is None or l is None:
            return 0.0
        return round(t - l, 2)

    def _fetch_12m_return(self, ticker: str) -> float | None:
        try:
            import yfinance as yf
            hist = yf.Ticker(ticker).history(period="1y")
            if hist.empty or len(hist) < 20:
                return None
            start = float(hist["Close"].iloc[0])
            end = float(hist["Close"].iloc[-1])
            return (end / start - 1) * 100 if start > 0 else None
        except Exception:
            return None

    def score_all_leaves(self, trunk: str) -> list[tuple[str, float, float]]:
        """Return [(leaf, bottleneck_score, discovery_lag_pct)] sorted by lag desc."""
        from equities.research.supply_chain import BottleneckScorer, get_leaves_for_trunk
        scorer = BottleneckScorer()
        return sorted(
            [(leaf, scorer.score(leaf, trunk), self.compute(trunk, leaf))
             for leaf in get_leaves_for_trunk(trunk)],
            key=lambda x: x[2],
            reverse=True,
        )
```

---

- [ ] **Step 9.5: Run supply chain and discovery lag tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_supply_chain.py tests/test_discovery_lag.py -v`
Expected: All PASS

---

- [ ] **Step 9.6: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/research/ tests/test_supply_chain.py tests/test_discovery_lag.py && git commit -m "feat(research): supply chain graph, BottleneckScorer, DiscoveryLagCalculator"
```

---

## Task 10: ThesisMiner — LLM-Generated Supply Chain Beneficiaries

**What:** Weekly LLM run that takes structural theses and generates tickers at each supply chain level. Output feeds `runner_research.py` and extends the screening universe.

**Files:**
- Create: `equities/research/thesis_miner.py`
- Create: `runner_research.py`
- Create: `tests/test_thesis_miner.py`

---

- [ ] **Step 10.1: Write failing tests**

```python
# tests/test_thesis_miner.py
from __future__ import annotations

import json
from equities.research.thesis_miner import ThesisMiner
from equities.analysis.analyst import LLMResponse


class _StubLLM:
    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({
                "trunk": "NVDA",
                "level_1": ["AVGO", "AMD", "TSM"],
                "level_2": ["MU", "ALAB", "MRVL"],
                "level_3": ["AMKR", "COHR", "ENTG"],
                "reasoning": "AI inference growth drives demand.",
            }),
            input_tokens=300,
            output_tokens=150,
        )


def test_thesis_miner_returns_result():
    miner = ThesisMiner(_StubLLM())
    result = miner.mine("AI inference scales 100x")
    assert result.trunk == "NVDA"
    assert "AMD" in result.level_1
    assert "MU" in result.level_2
    assert "COHR" in result.level_3


def test_thesis_miner_all_tickers_no_duplicates():
    miner = ThesisMiner(_StubLLM())
    result = miner.mine("AI inference scales 100x")
    all_t = result.all_tickers()
    assert len(all_t) == len(set(all_t))
    assert "AVGO" in all_t
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_thesis_miner.py -v`
Expected: FAIL

---

- [ ] **Step 10.2: Create `equities/research/thesis_miner.py`**

```python
"""ThesisMiner — LLM generates supply chain beneficiaries from structural theses."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from equities.analysis.analyst import LLMResponse


STRUCTURAL_THESES = [
    "AI inference compute scales 100x by 2027, requiring massive GPU, memory, power, and cooling infrastructure",
    "GLP-1 obesity drugs penetrate 15% of US adults by 2028, reshaping healthcare delivery and diagnostics",
    "US domestic semiconductor fabrication doubles by 2027 under CHIPS Act, benefiting equipment and materials",
    "AI-driven grid infrastructure spending reaches $500B over 5 years, requiring transformers, cables, power ICs",
    "Autonomous defense systems replace 20% of manned platforms by 2028, requiring AI chips, sensors, connectivity",
]

_SYSTEM = """You are a supply chain analyst identifying US-listed equities benefiting from a structural thesis.

Return:
- trunk: single most direct beneficiary (NYSE/NASDAQ ticker)
- level_1: 3-5 direct suppliers or close peers
- level_2: 3-5 suppliers to level_1 (one step deeper, less obvious)
- level_3: 3-5 suppliers to level_2 (deepest, most overlooked — prefer small/mid cap)

Rules: US tickers only. Each level less correlated to trunk than previous.

Return ONLY valid JSON. No markdown."""

_USER = """Thesis: {thesis}

Output:
{{
  "trunk": "TICKER",
  "level_1": ["T1","T2","T3"],
  "level_2": ["T4","T5","T6"],
  "level_3": ["T7","T8","T9"],
  "reasoning": "2-3 sentences"
}}"""


class LLMClient(Protocol):
    def complete(self, system: str, user: str, model: str) -> LLMResponse: ...


@dataclass
class ThesisResult:
    thesis: str
    trunk: str
    level_1: list[str] = field(default_factory=list)
    level_2: list[str] = field(default_factory=list)
    level_3: list[str] = field(default_factory=list)
    reasoning: str = ""

    def all_tickers(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for t in self.level_1 + self.level_2 + self.level_3:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result


class ThesisMiner:
    _SONNET = "claude-sonnet-4-6"

    def __init__(self, llm: LLMClient | None = None) -> None:
        if llm is None:
            from core.claude_client import ClaudeCodeClient
            llm = ClaudeCodeClient()  # type: ignore[assignment]
        self._llm = llm

    def mine(self, thesis: str) -> ThesisResult:
        resp = self._llm.complete(_SYSTEM, _USER.format(thesis=thesis), self._SONNET)
        text = resp.content.strip()
        if text.startswith("```"):
            text = "\n".join(l for l in text.splitlines()[1:] if not l.startswith("```"))
        data = json.loads(text)
        return ThesisResult(
            thesis=thesis,
            trunk=data.get("trunk", ""),
            level_1=data.get("level_1", []),
            level_2=data.get("level_2", []),
            level_3=data.get("level_3", []),
            reasoning=data.get("reasoning", ""),
        )

    def mine_all(self) -> list[ThesisResult]:
        results = []
        for thesis in STRUCTURAL_THESES:
            try:
                results.append(self.mine(thesis))
            except Exception:
                continue
        return results
```

---

- [ ] **Step 10.3: Create `runner_research.py`**

```python
"""Weekly research runner — mines supply chain theses and scores discovery lags.

Usage:
    uv run python runner_research.py

Writes top 50 research candidates to data/research_candidates.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from equities.research.thesis_miner import ThesisMiner
from equities.research.discovery_lag import DiscoveryLagCalculator
from equities.research.supply_chain import BottleneckScorer, SUPPLY_CHAIN


def main() -> None:
    Path("data").mkdir(exist_ok=True)
    miner = ThesisMiner()
    lag = DiscoveryLagCalculator()
    scorer = BottleneckScorer()

    print("=== ThesisMiner ===\n")
    all_candidates: list[dict] = []
    for result in miner.mine_all():
        print(f"Thesis: {result.thesis[:80]}...")
        print(f"  Trunk={result.trunk}  L1={result.level_1}  L2={result.level_2}  L3={result.level_3}")
        for level, tickers in [("L1", result.level_1), ("L2", result.level_2), ("L3", result.level_3)]:
            for ticker in tickers:
                d_lag = lag.compute(result.trunk, ticker)
                b_score = scorer.score(ticker, result.trunk)
                all_candidates.append({
                    "ticker": ticker,
                    "trunk": result.trunk,
                    "level": level,
                    "discovery_lag_pct": d_lag,
                    "bottleneck_score": b_score,
                    "opportunity_score": round((d_lag / 100) * b_score, 4),
                    "thesis": result.thesis[:100],
                })

    print("\n=== Static supply chain discovery lag (top 4 trunks) ===")
    for trunk in list(SUPPLY_CHAIN.keys())[:4]:
        print(f"\n{trunk}:")
        for leaf, b, d in lag.score_all_leaves(trunk)[:5]:
            print(f"  {leaf}  bottleneck={b:.2f}  lag={d:+.1f}pp")

    all_candidates.sort(key=lambda x: x["opportunity_score"], reverse=True)
    out = Path("data/research_candidates.json")
    out.write_text(json.dumps(all_candidates[:50], indent=2))
    print(f"\nTop 50 saved to {out}")


if __name__ == "__main__":
    main()
```

---

- [ ] **Step 10.4: Run tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_thesis_miner.py -v`
Expected: All PASS

---

- [ ] **Step 10.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/research/thesis_miner.py runner_research.py tests/test_thesis_miner.py && git commit -m "feat(research): ThesisMiner + runner_research.py weekly supply chain intelligence"
```

---

## Task 11: Narrative Gap Detector

**What:** Detect tickers where recent news contains "new economy" vocabulary (AI, data center, backlog) that doesn't match the company's established sector narrative. Low analyst coverage amplifies the signal.

**Files:**
- Create: `equities/research/narrative_gap.py`
- Create: `tests/test_narrative_gap.py`

---

- [ ] **Step 11.1: Write failing tests**

```python
# tests/test_narrative_gap.py
from __future__ import annotations

from equities.research.narrative_gap import NarrativeGapDetector


def test_ai_vocabulary_in_industrial_sector_flagged():
    detector = NarrativeGapDetector()
    headlines = [
        "Eaton lands $200M AI data center power deal",
        "Record backlog driven by hyperscaler demand",
        "AI infrastructure buildout fuels transformer orders",
    ]
    score = detector.detect("ETN", headlines, sector="Industrials", analyst_count=30)
    assert score > 0.5


def test_ai_vocab_in_tech_sector_not_flagged():
    detector = NarrativeGapDetector()
    headlines = ["NVIDIA announces new AI chip", "NVIDIA data center revenue triples"]
    score = detector.detect("NVDA", headlines, sector="Semiconductors", analyst_count=60)
    assert score < 0.3


def test_no_headlines_returns_zero():
    detector = NarrativeGapDetector()
    assert detector.detect("XYZ", [], "Energy", analyst_count=5) == 0.0


def test_low_coverage_amplifies_score():
    detector = NarrativeGapDetector()
    hl = ["AI-powered automation drives record orders"]
    low = detector.detect("KLIC", hl, "Semiconductors", analyst_count=3)
    high = detector.detect("KLIC", hl, "Semiconductors", analyst_count=50)
    assert low > high
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_narrative_gap.py -v`
Expected: FAIL

---

- [ ] **Step 11.2: Create `equities/research/narrative_gap.py`**

```python
"""Narrative gap detector — surface stocks where news suggests a new story
not yet reflected in analyst consensus."""
from __future__ import annotations

_NEW_ECONOMY_TERMS: set[str] = {
    "ai", "artificial intelligence", "data center", "automation",
    "robotics", "autonomous", "machine learning", "llm", "gpu",
    "backlog", "sold out", "record orders", "capacity constrained",
    "hyperscaler", "inference", "generative", "foundation model",
    "power demand", "grid upgrade", "nuclear", "energy transition",
}

_HIGH_TECH_SECTORS: set[str] = {
    "semiconductors", "technology", "software",
    "information technology", "communication services",
}


class NarrativeGapDetector:
    """Score 0.0-1.0. Above 0.5 = meaningful narrative gap."""

    def detect(
        self,
        ticker: str,  # noqa: ARG002
        headlines: list[str],
        sector: str,
        analyst_count: int,
    ) -> float:
        if not headlines:
            return 0.0

        all_text = " ".join(h.lower() for h in headlines)
        matched = sum(1 for t in _NEW_ECONOMY_TERMS if t in all_text)
        vocab_score = min(1.0, matched / 4.0)
        if vocab_score == 0.0:
            return 0.0

        is_high_tech = any(s in sector.lower() for s in _HIGH_TECH_SECTORS)
        sector_multiplier = 0.3 if is_high_tech else 1.0

        if analyst_count <= 3:
            coverage_amp = 1.5
        elif analyst_count <= 8:
            coverage_amp = 1.2
        elif analyst_count <= 20:
            coverage_amp = 1.0
        else:
            coverage_amp = 0.7

        return round(min(1.0, vocab_score * sector_multiplier * coverage_amp), 4)
```

---

- [ ] **Step 11.3: Run narrative gap tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_narrative_gap.py -v`
Expected: All PASS

---

- [ ] **Step 11.4: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/research/narrative_gap.py tests/test_narrative_gap.py && git commit -m "feat(research): NarrativeGapDetector — vocabulary-shift signal for narrative plays"
```

---

# Phase 4: Monitoring Upgrades

## Task 12: Thesis Health Checker (Nightly)

**What:** LLM checks each open swing position's thesis against latest headlines. Returns `intact/degraded/invalidated` + `hold/reduce/exit`. Triggers thesis-based exits before price stop fires.

**Files:**
- Create: `equities/killgate/thesis_health.py`
- Modify: `runner_equities.py`
- Create: `tests/test_thesis_health.py`

---

- [ ] **Step 12.1: Write failing tests**

```python
# tests/test_thesis_health.py
from __future__ import annotations

import json
from equities.killgate.thesis_health import ThesisHealthChecker, ThesisHealth
from equities.analysis.analyst import LLMResponse


class _LLM:
    def __init__(self, status: str, action: str, reason: str) -> None:
        self._d = {"status": status, "action": action, "reason": reason}

    def complete(self, s: str, u: str, m: str) -> LLMResponse:
        return LLMResponse(content=json.dumps(self._d), input_tokens=200, output_tokens=80)


_POS = {"id": "p1", "ticker": "KLIC", "thesis": "Bottleneck play", "catalyst": "Earnings", "entry_price": 50.0, "sleeve": "swing"}


def test_intact_returns_hold():
    checker = ThesisHealthChecker(_LLM("intact", "hold", "No change"))
    r = checker.check(_POS, ["KLIC steady"])
    assert r.status == "intact"
    assert r.action == "hold"


def test_invalidated_returns_exit():
    checker = ThesisHealthChecker(_LLM("invalidated", "exit", "Already priced in"))
    r = checker.check(_POS, ["KLIC up 40%"])
    assert r.status == "invalidated"
    assert r.action == "exit"


def test_failed_llm_defaults_to_hold():
    class _FailLLM:
        def complete(self, s: str, u: str, m: str) -> LLMResponse:
            raise RuntimeError("network error")

    checker = ThesisHealthChecker(_FailLLM())
    r = checker.check(_POS, [])
    assert r.action == "hold"
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_thesis_health.py -v`
Expected: FAIL

---

- [ ] **Step 12.2: Create `equities/killgate/thesis_health.py`**

```python
"""Nightly thesis health checker — exits positions on thesis invalidation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from equities.analysis.analyst import LLMResponse


_SYSTEM = """You are a portfolio risk officer reviewing an open swing position.
Determine whether the original entry thesis is still intact, degraded, or invalidated.

intact: no new information materially changes the thesis
degraded: 1-2 concerns reduce the edge but core thesis holds
invalidated: catalyst gone, fully priced in, or contradictory event occurred

Return ONLY valid JSON. No markdown."""

_USER = """Review this open position.

## Position
Ticker: {ticker}
Original thesis: {thesis}
Original catalyst: {catalyst}
Entry price: ${entry_price:.2f}

## Recent news
{headlines_block}

Output:
{{
  "status": "intact" | "degraded" | "invalidated",
  "action": "hold" | "reduce" | "exit",
  "reason": "one sentence"
}}"""


class LLMClient(Protocol):
    def complete(self, system: str, user: str, model: str) -> LLMResponse: ...


@dataclass(frozen=True)
class ThesisHealth:
    position_id: str
    ticker: str
    status: str
    action: str
    reason: str


class ThesisHealthChecker:
    _HAIKU = "claude-haiku-4-5-20251001"

    def __init__(self, llm: LLMClient | None = None) -> None:
        if llm is None:
            from core.claude_client import ClaudeCodeClient
            llm = ClaudeCodeClient()  # type: ignore[assignment]
        self._llm = llm

    def check(self, position: dict, headlines: list[str]) -> ThesisHealth:
        headlines_block = "\n".join(f"- {h}" for h in headlines[:10]) or "  (none)"
        user_msg = _USER.format(
            ticker=position.get("ticker", ""),
            thesis=position.get("thesis", ""),
            catalyst=position.get("catalyst", ""),
            entry_price=position.get("entry_price", 0.0),
            headlines_block=headlines_block,
        )
        try:
            resp = self._llm.complete(_SYSTEM, user_msg, self._HAIKU)
            data = json.loads(resp.content.strip())
        except Exception:
            return ThesisHealth(
                position_id=position.get("id", ""),
                ticker=position.get("ticker", ""),
                status="intact",
                action="hold",
                reason="health_check_failed_defaulting_to_hold",
            )
        return ThesisHealth(
            position_id=position.get("id", ""),
            ticker=position.get("ticker", ""),
            status=data.get("status", "intact"),
            action=data.get("action", "hold"),
            reason=data.get("reason", ""),
        )

    def check_all(self, open_positions: list[dict], news_provider: object) -> list[ThesisHealth]:
        results: list[ThesisHealth] = []
        for pos in open_positions:
            if pos.get("sleeve") != "swing":
                continue
            try:
                headlines = news_provider.headlines(pos.get("ticker", ""), limit=10)  # type: ignore
            except Exception:
                headlines = []
            results.append(self.check(pos, headlines))
        return results
```

---

- [ ] **Step 12.3: Run tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_thesis_health.py -v`
Expected: All PASS

---

- [ ] **Step 12.4: Wire into `runner_equities.py`**

In `run_once()`, before the screen stage, add:

```python
    from equities.killgate.thesis_health import ThesisHealthChecker
    open_swing = [p for p in equity_ledger.open_positions() if p.get("sleeve") == "swing"]
    if open_swing and not mark_only:
        health_checker = ThesisHealthChecker()
        for health in health_checker.check_all(open_swing, news):
            print(f"  [HEALTH] {health.ticker}: {health.status} -> {health.action} | {health.reason}")
            if health.action == "exit":
                paper.force_close(health.position_id, reason=f"thesis_invalidated: {health.reason}")
                if alerts is not None:
                    await alerts.send(f"Thesis exit: {health.ticker} — {health.reason}")
```

---

- [ ] **Step 12.5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/killgate/thesis_health.py runner_equities.py tests/test_thesis_health.py && git commit -m "feat(monitoring): ThesisHealthChecker exits positions on thesis invalidation"
```

---

## Task 13: Thematic Concentration Monitor

**What:** Detect when open portfolio has >35% in a single supply chain theme (e.g. all NVDA-chain stocks). Complements the sector check — you can hold NVDA + AVGO + COHR all in different sectors but they're the same theme.

**Files:**
- Create: `equities/screen/thematic_monitor.py`
- Create: `tests/test_thematic_monitor.py`

---

- [ ] **Step 13.1: Write failing tests**

```python
# tests/test_thematic_monitor.py
from __future__ import annotations

from equities.screen.thematic_monitor import ThematicMonitor


def test_no_concentration_no_alerts():
    monitor = ThematicMonitor(max_theme_pct=0.35, capital=100_000)
    open_positions = [
        {"ticker": "MU",   "shares": 100, "entry_price": 100.0},   # $10k NVDA chain
        {"ticker": "COHR", "shares": 80,  "entry_price": 80.0},    # $6.4k NVDA chain
        {"ticker": "CRWD", "shares": 50,  "entry_price": 200.0},   # $10k MSFT chain
    ]
    assert monitor.check(open_positions) == []


def test_over_threshold_returns_alert():
    monitor = ThematicMonitor(max_theme_pct=0.20, capital=100_000)
    open_positions = [
        {"ticker": "MU",   "shares": 100, "entry_price": 120.0},   # $12k NVDA chain
        {"ticker": "COHR", "shares": 100, "entry_price": 80.0},    # $8k NVDA chain = $20k = 20%
        {"ticker": "AMKR", "shares": 100, "entry_price": 30.0},    # $3k pushes to 23% > 20%
    ]
    alerts = monitor.check(open_positions)
    assert len(alerts) == 1
    assert "NVDA" in alerts[0]


def test_ticker_not_in_chain_ignored():
    monitor = ThematicMonitor(max_theme_pct=0.35, capital=100_000)
    assert monitor.check([{"ticker": "AAPL", "shares": 100, "entry_price": 200.0}]) == []
```

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_thematic_monitor.py -v`
Expected: FAIL

---

- [ ] **Step 13.2: Create `equities/screen/thematic_monitor.py`**

```python
"""Thematic concentration monitor — uses supply chain graph to detect theme over-concentration."""
from __future__ import annotations

from equities.research.supply_chain import get_trunks_for_leaf


class ThematicMonitor:
    def __init__(self, max_theme_pct: float = 0.35, capital: float = 10_000.0) -> None:
        self._max = max_theme_pct
        self._capital = capital

    def check(self, open_positions: list[dict]) -> list[str]:
        theme_exposure: dict[str, float] = {}
        for pos in open_positions:
            ticker = pos.get("ticker", "")
            value = pos.get("shares", 0) * pos.get("entry_price", 0.0)
            trunks = get_trunks_for_leaf(ticker)
            if not trunks:
                continue
            per_trunk = value / len(trunks)
            for trunk in trunks:
                theme_exposure[trunk] = theme_exposure.get(trunk, 0.0) + per_trunk

        alerts: list[str] = []
        for trunk, exposure in theme_exposure.items():
            pct = exposure / self._capital
            if pct > self._max:
                alerts.append(
                    f"Thematic concentration: {trunk} chain = {pct:.1%} > limit {self._max:.0%}"
                )
        return alerts
```

---

- [ ] **Step 13.3: Run tests**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/test_thematic_monitor.py -v`
Expected: All PASS

---

- [ ] **Step 13.4: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add equities/screen/thematic_monitor.py tests/test_thematic_monitor.py && git commit -m "feat(monitoring): ThematicMonitor detects supply chain theme concentration"
```

---

## Task 14: Integration + Smoke Test

- [ ] **Step 14.1: Run full test suite**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run pytest tests/ -v --tb=short`
Expected: All pass.

---

- [ ] **Step 14.2: Smoke test runner (no Claude calls)**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run python runner_equities.py --no-analyse`
Expected: Completes without error. Prints VIX reading, inflection candidates, swing + core candidates.

---

- [ ] **Step 14.3: Smoke test research runner**

Run: `cd /Users/nikolassapalidis/polymarket-bot && uv run python runner_research.py`
Expected: Calls ThesisMiner (one Claude call per thesis), prints supply chain DAGs, writes `data/research_candidates.json`.

---

- [ ] **Step 14.4: Final commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot && git add -u && git commit -m "chore: Phase 4 complete — full research + analysis + monitoring upgrade"
```

---

## Summary

| Phase | Tasks | Key Deliverable |
|---|---|---|
| 1 — Analysis Hardening | 1–4 | Auditor agent, signal fusion, analyst_count injection, sector concentration fuse |
| 2 — Data Enrichment | 5–8 | Enriched fundamentals, multi-source news, VIX gate, InflectionScanner |
| 3 — Research Intelligence | 9–11 | Supply chain graph, discovery lag, ThesisMiner, NarrativeGapDetector |
| 4 — Monitoring | 12–13 | ThesisHealthChecker, ThematicMonitor |
| Integration | 14 | Full test suite + runner smoke tests |

---

## Remaining Gaps (Out of Scope for This Plan)

**Research not yet perfected:**
- Options flow (Unusual Whales API, ~$30/mo) — adds informed-money signal before Haiku prefilter runs
- Earnings transcript parsing — requires transcript API or EDGAR 8-K scraping
- Dynamic universe expansion (Russell 1000 screening vs. hand-curated 90-stock list)

**Analysis not yet perfected:**
- Specialist agent split: Fundamental / Technical / Catalyst agents producing independent scores then fused — natural Phase 5 extension of the signal fusion formula from Task 2
- Macro context agent: reads Fed calendar, yield curve, sector rotation before analysis
