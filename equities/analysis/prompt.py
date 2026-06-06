"""Prompt builders for the equity analyst pipeline (swing + core DCA + challenger)."""
from __future__ import annotations

from equities.screen.event_screen import CandidateEvent
from equities.screen.quality_screen import QualityCandidate

# ---------------------------------------------------------------------------
# Stage 1 — Haiku prefilter
# ---------------------------------------------------------------------------

_PREFILTER_SYSTEM = """You are a quantitative research screener for a systematic equity trading system.
Evaluate each candidate and score it 1-10 for its potential as a 1-4 week swing trade.

Score criteria:
- 8-10: Clear near-term binary catalyst, under-followed (< 5 analysts), well-defined entry thesis
- 5-7: Interesting but story may be partially priced; worth deep analysis
- 1-4: REJECT — catalyst already fully reflected in price, routine admin filing, or large-cap with full coverage

Return ONLY valid JSON: {"rankings": [{"ticker": "TICKER", "score": 7, "reason": "one sentence"}]}
No markdown fences, no commentary outside the JSON object."""

_PREFILTER_USER = """Score each of these equity catalysts. Under-followed stocks (< 5 sell-side analysts) deserve a coverage bonus of +1 to your score — the market is less informed.

{candidates_block}

Return JSON rankings."""


def build_prefilter_prompt(
    candidates: list[CandidateEvent],
    analyst_counts: dict[str, int] | None = None,
) -> str:
    """Build the Haiku prefilter user message."""
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


# ---------------------------------------------------------------------------
# Stage 2 — Sonnet deep analyst
# ---------------------------------------------------------------------------

_ANALYST_SYSTEM = """You are a systematic equity analyst. Your #1 rule:

**REJECT any setup where the re-rating is already complete.**
If the stock has moved >15% in the 5 days after the catalyst emerged, the smart money has already acted. Write "REJECT: already priced in."

You evaluate events that may cause a re-rating over a 1-4 week horizon. You do NOT predict macro or direction — you identify situations where the market has not yet finished pricing a specific catalyst.

Output ONLY valid JSON. No markdown, no preamble."""

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

## Macro context
Regime: {macro_regime} | VIX: {vix_str} | Yield curve (10y-3m): {yield_curve_str}
{specialist_section}
{sentiment_section}
{memory_section}

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
  "thesis": "<2-3 sentences: what the market is missing>",
  "business_quality": "<specific evidence on product, margins, growth, or competitive position>",
  "valuation": "<specific valuation or expectation evidence, or why valuation is not decisive>",
  "balance_sheet_risk": "<specific leverage, liquidity, dilution, or cash-flow risk evidence>",
  "market_expectation_gap": "<what consensus or recent price action appears to miss>",
  "invalidation": "<concrete fact, price action, filing, or result that would break the thesis>",
  "evidence_citations": ["headline, filing, metric, or prompt fact used", "another concrete citation"]
}}

Reject if the memo would be generic or uncited. Every buy must cite concrete prompt evidence."""


def build_analyst_prompt(
    candidate: CandidateEvent,
    current_price: float,
    news: list[str],
    filings: list[str],
    sector: str = "",
    analyst_count: int = 0,
    macro_regime: str = "neutral",
    vix: float | None = None,
    yield_curve: float | None = None,
    memory_block: str = "",
    sentiment_block: str = "",
    specialist_block: str = "",
) -> str:
    """Build the Sonnet deep-analyst user message."""
    news_block = "\n".join(f"- {h}" for h in news[:8]) or "  (none)"
    filings_block = "\n".join(f"- {f}" for f in filings[:5]) or "  (none)"
    vix_str = f"{vix:.1f}" if vix is not None else "n/a"
    yield_curve_str = f"{yield_curve:.2f}" if yield_curve is not None else "n/a"
    memory_section = (
        f"\n\n## Decision memory\n{memory_block.strip()}" if memory_block.strip() else ""
    )
    sentiment_section = (
        f"\n\n## Sentiment snapshot\n{sentiment_block.strip()}"
        if sentiment_block.strip()
        else ""
    )
    specialist_section = (
        f"\n\n## Specialist packets\n{specialist_block.strip()}"
        if specialist_block.strip()
        else ""
    )
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
        macro_regime=macro_regime,
        vix_str=vix_str,
        yield_curve_str=yield_curve_str,
        specialist_section=specialist_section,
        sentiment_section=sentiment_section,
        memory_section=memory_section,
    )


# ---------------------------------------------------------------------------
# Stage 3 — Sonnet challenger (argue against the bull thesis)
# ---------------------------------------------------------------------------

_CHALLENGER_SYSTEM = """You are a bearish equity analyst stress-testing a proposed trade.
Your job: find the strongest specific objections to this thesis.
No generic risks ("market could fall", "competition exists"). Only concrete, ticker-specific reasons this trade fails.

Return ONLY valid JSON. No markdown, no preamble."""

_CHALLENGER_USER = """Challenge this proposed swing trade.

## Proposed Trade
Ticker: {ticker}
Entry: ${entry:.2f} | Stop: ${stop:.2f} | Target: ${target:.2f}
Catalyst: {catalyst}
Bull thesis: {thesis}

## Recent news
{news_block}

Output:
{{
  "verdict": "reject" | "weaken" | "pass",
  "objections": ["specific objection 1", "specific objection 2"],
  "confidence_adjustment": <float between -0.3 and 0.0>,
  "summary": "one sentence verdict"
}}

Verdict rules:
- "reject": thesis is fundamentally flawed or catalyst is already fully priced in
- "weaken": 1-2 real concerns reduce the edge but do not eliminate it
- "pass": no material objections — bull case stands"""


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


def build_challenger_prompt(
    ticker: str,
    entry: float,
    stop: float,
    target: float,
    catalyst: str,
    thesis: str,
    news: list[str],
) -> str:
    news_block = "\n".join(f"- {h}" for h in news[:10]) or "  (none)"
    return _CHALLENGER_USER.format(
        ticker=ticker,
        entry=entry,
        stop=stop,
        target=target,
        catalyst=catalyst,
        thesis=thesis,
        news_block=news_block,
    )


# ---------------------------------------------------------------------------
# Core DCA analyst — risk-officer check before accumulating
# ---------------------------------------------------------------------------

_CORE_DCA_SYSTEM = """You are a risk officer reviewing DCA accumulation candidates for a long-term systematic portfolio.
The quality screener already confirmed strong fundamentals. Your only job: flag specific near-term reasons to WAIT.

You do NOT need a catalyst to approve a DCA. Approve unless there is a concrete, near-term risk.

Return ONLY valid JSON. No markdown, no preamble."""

_CORE_DCA_USER = """Review this DCA accumulation candidate.

## Company
Ticker: {ticker}
Quality score: {score:.3f}/1.0
Fundamentals: {evidence}
Current price: ${current_price:.2f}
{reviewer_section}

## Recent news (last 15 headlines)
{news_block}

Output:
{{
  "action": "dca" | "wait",
  "risk_flags": ["specific risk 1", "specific risk 2"],
  "dca_pct": <float, 0.005 to 0.015>,
  "thesis": "one sentence: why accumulate now or why to wait"
}}

Wait only if there is: earnings warning, SEC investigation, major lawsuit, product recall,
CFO/CEO departure + no replacement, or sector-wide regulatory crisis.
Everything else → "dca"."""


def build_core_dca_prompt(
    candidate: QualityCandidate,
    current_price: float,
    news: list[str],
    reviewer_block: str = "",
) -> str:
    news_block = "\n".join(f"- {h}" for h in news[:15]) or "  (none)"
    reviewer_section = (
        f"\n\n## Deterministic reviewer checks\n{reviewer_block.strip()}"
        if reviewer_block.strip()
        else ""
    )
    return _CORE_DCA_USER.format(
        ticker=candidate.instrument.ticker,
        score=candidate.score,
        evidence=candidate.evidence,
        current_price=current_price,
        reviewer_section=reviewer_section,
        news_block=news_block,
    )
