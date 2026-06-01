"""07c — Two-stage equity analyst: Haiku prefilter → Sonnet thesis.

Stage 1 (Haiku): Score all candidates cheaply, keep top `max_candidates`.
Stage 2 (Sonnet): For each survivor, write thesis + entry/stop/TP.

Daily budget guard prevents runaway spend. When the budget is exhausted,
remaining candidates are skipped for the day.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from core.assets.instrument import Instrument
from equities.analysis.budget import DailyBudget
from equities.analysis.prompt import (
    _ANALYST_SYSTEM,
    _PREFILTER_SYSTEM,
    build_analyst_prompt,
    build_prefilter_prompt,
)
from equities.screen.event_screen import CandidateEvent
from equities.strategy import Recommendation, Sleeve

# ---------------------------------------------------------------------------
# LLM client protocol (injectable for testing)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int

    def cost_usd(self, model: str = "sonnet") -> float:
        if "haiku" in model:
            return self.input_tokens * 8e-7 + self.output_tokens * 4e-6
        return self.input_tokens * 3e-6 + self.output_tokens * 1.5e-5


class LLMClient(Protocol):
    def complete(self, system: str, user: str, model: str) -> LLMResponse: ...


class AnthropicLLMClient:
    """Real Anthropic SDK client. Requires ANTHROPIC_API_KEY in env."""

    def __init__(self, api_key: str) -> None:
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key)

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        resp = self._client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text if resp.content else ""
        return LLMResponse(
            content=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )


# ---------------------------------------------------------------------------
# Data providers (injected — real implementations in equities/data/)
# ---------------------------------------------------------------------------

class PriceProvider(Protocol):
    def latest_close(self, ticker: str) -> float | None: ...


class NewsProvider(Protocol):
    def headlines(self, ticker: str, limit: int = 8) -> list[str]: ...


class FilingsSummaryProvider(Protocol):
    def summary(self, ticker: str, days: int = 90) -> list[str]: ...


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------

_HAIKU = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"
_HAIKU_COST_PER_CANDIDATE = 0.0005  # estimated cost per Haiku call
_SONNET_COST_PER_CANDIDATE = 0.01   # estimated cost per Sonnet call


class EquityAnalyst:
    """Two-stage equity analyst with daily budget guard.

    Stage 1: Haiku scores all candidates and returns top `max_candidates`.
    Stage 2: Sonnet writes entry/stop/TP for each surviving candidate.
    Candidates where the re-rating is already complete are rejected.

    When `llm` is None, uses ClaudeCodeClient (Claude subscription via
    `claude -p`) — no API key required.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        prices: PriceProvider | None = None,
        news: NewsProvider | None = None,
        filings: FilingsSummaryProvider | None = None,
        budget: DailyBudget | None = None,
        max_candidates: int = 5,
    ) -> None:
        if llm is None:
            from core.claude_client import ClaudeCodeClient
            llm = ClaudeCodeClient()  # type: ignore[assignment]
        self._llm = llm
        self._prices = prices
        self._news = news
        self._filings = filings
        self._budget = budget or DailyBudget(daily_limit_usd=1.0)
        self._max_candidates = max_candidates

    def analyse(self, candidates: list[CandidateEvent]) -> list[Recommendation]:
        """Run the two-stage pipeline. Returns Recommendations (may be fewer than input)."""
        if not candidates:
            return []

        # Stage 1: Haiku prefilter
        survivors = self._prefilter(candidates)

        # Stage 2: Sonnet deep analysis
        results: list[Recommendation] = []
        for candidate in survivors:
            if not self._budget.allow(_SONNET_COST_PER_CANDIDATE):
                break  # daily budget exhausted
            rec = self._analyse_one(candidate)
            if rec is not None:
                results.append(rec)

        return results

    def _prefilter(self, candidates: list[CandidateEvent]) -> list[CandidateEvent]:
        if not self._budget.allow(_HAIKU_COST_PER_CANDIDATE):
            return candidates[: self._max_candidates]  # fallback: take first N

        user_msg = build_prefilter_prompt(candidates)
        try:
            resp = self._llm.complete(_PREFILTER_SYSTEM, user_msg, _HAIKU)
            self._budget.record(resp.cost_usd("haiku"))
            parsed = json.loads(resp.content)
            rankings = parsed.get("rankings", [])
            # Map ticker → score
            scores: dict[str, int] = {r["ticker"]: r.get("score", 0) for r in rankings}
            ranked = sorted(candidates, key=lambda c: scores.get(c.instrument.ticker, 0), reverse=True)
            return ranked[: self._max_candidates]
        except (json.JSONDecodeError, KeyError, Exception):
            # On any failure, fall back to urgency ordering (already sorted by caller)
            return candidates[: self._max_candidates]

    def _analyse_one(self, candidate: CandidateEvent) -> Recommendation | None:
        ticker = candidate.instrument.ticker
        price = self._prices.latest_close(ticker) or 0.0
        headlines = self._news.headlines(ticker, limit=8)
        filings = self._filings.summary(ticker, days=90)

        user_msg = build_analyst_prompt(candidate, price, headlines, filings)
        try:
            resp = self._llm.complete(_ANALYST_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            raw = _strip_fences(resp.content)
            data = json.loads(raw)
        except Exception:
            return None

        if data.get("action") == "reject":
            return None  # re-rating already complete

        if data.get("action") != "buy":
            return None

        try:
            return Recommendation(
                instrument=candidate.instrument,
                sleeve=Sleeve.SWING,
                side="buy",
                entry=float(data["entry"]),
                stop_loss=float(data["stop_loss"]),
                take_profit=float(data["take_profit"]),
                size_pct=0.02,  # fixed 2% risk; kernel will compute exact shares
                confidence=float(data.get("confidence", 0.5)),
                catalyst=str(data.get("catalyst", candidate.evidence)),
                thesis=str(data.get("thesis", "")),
                horizon=str(data.get("horizon", "1-2 weeks")),
            )
        except (KeyError, TypeError, ValueError):
            return None


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first and last fence lines
        inner = [l for l in lines[1:] if not l.startswith("```")]
        return "\n".join(inner)
    return text
