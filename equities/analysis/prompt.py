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

_PREFILTER_USER = """Score each of these equity catalysts:

{candidates_block}

Return JSON rankings."""


def build_prefilter_prompt(candidates: list[CandidateEvent]) -> str:
    """Build the Haiku prefilter user message."""
    lines = []
    for c in candidates:
        lines.append(
            f"- {c.instrument.ticker} ({c.instrument.cap_tier.value} cap): "
            f"{c.event_type.value} | {c.evidence}"
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
  "stop_loss": <stop price — where thesis is broken>,
  "take_profit": <target — where re-rating completes>,
  "confidence": <0.0-1.0>,
  "horizon": "<e.g. 1-2 weeks>",
  "catalyst": "<one sentence: what specific event drives this>",
  "thesis": "<2-3 sentences: what the market is missing, why the re-rating is incomplete>"
}}"""


def build_analyst_prompt(
    candidate: CandidateEvent,
    current_price: float,
    news: list[str],
    filings: list[str],
) -> str:
    """Build the Sonnet deep-analyst user message."""
    news_block = "\n".join(f"- {h}" for h in news[:15]) or "  (none)"
    filings_block = "\n".join(f"- {f}" for f in filings[:6]) or "  (none)"
    return _ANALYST_USER.format(
        ticker=candidate.instrument.ticker,
        event_type=candidate.event_type.value,
        evidence=candidate.evidence,
        current_price=current_price,
        cap_tier=candidate.instrument.cap_tier.value,
        news_block=news_block,
        filings_block=filings_block,
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
) -> str:
    news_block = "\n".join(f"- {h}" for h in news[:15]) or "  (none)"
    return _CORE_DCA_USER.format(
        ticker=candidate.instrument.ticker,
        score=candidate.score,
        evidence=candidate.evidence,
        current_price=current_price,
        news_block=news_block,
    )
