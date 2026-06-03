"""07c — Three-stage equity analyst: Haiku prefilter → Sonnet thesis → Sonnet challenger.

Stage 1 (Haiku):      Score all candidates cheaply, keep top `max_candidates`.
Stage 2 (Sonnet):     For each survivor, write bull thesis + entry/stop/TP.
Stage 3 (Sonnet):     Challenger argues against the bull case; can reject or weaken.

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
    _CHALLENGER_SYSTEM,
    _PREFILTER_SYSTEM,
    build_analyst_prompt,
    build_challenger_prompt,
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
    def headlines(self, ticker: str, limit: int = 15) -> list[str]: ...


class FilingsSummaryProvider(Protocol):
    def summary(self, ticker: str, days: int = 90) -> list[str]: ...


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------

_HAIKU = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"
_HAIKU_COST_PER_CANDIDATE = 0.0005
_SONNET_COST_PER_CANDIDATE = 0.01
_CHALLENGER_COST = 0.008


class EquityAnalyst:
    """Three-stage equity analyst: prefilter → bull thesis → challenger.

    Stage 1: Haiku scores all candidates and returns top `max_candidates`.
    Stage 2: Sonnet writes entry/stop/TP for each surviving candidate.
    Stage 3: Sonnet challenger argues against the bull case.
              - "reject" → drop the trade
              - "weaken" → reduce confidence by objection delta
              - "pass"   → keep as-is

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
        """Run the three-stage pipeline. Returns Recommendations."""
        if not candidates:
            return []

        survivors = self._prefilter(candidates)

        results: list[Recommendation] = []
        for candidate in survivors:
            if not self._budget.allow(_SONNET_COST_PER_CANDIDATE + _CHALLENGER_COST):
                break
            rec = self._analyse_one(candidate)
            if rec is None:
                continue
            final = self._challenge(rec)
            if final is not None:
                results.append(final)

        return results

    def _prefilter(self, candidates: list[CandidateEvent]) -> list[CandidateEvent]:
        if not self._budget.allow(_HAIKU_COST_PER_CANDIDATE):
            return candidates[: self._max_candidates]

        user_msg = build_prefilter_prompt(candidates)
        try:
            resp = self._llm.complete(_PREFILTER_SYSTEM, user_msg, _HAIKU)
            self._budget.record(resp.cost_usd("haiku"))
            parsed = json.loads(resp.content)
            rankings = parsed.get("rankings", [])
            scores: dict[str, int] = {r["ticker"]: r.get("score", 0) for r in rankings}
            ranked = sorted(candidates, key=lambda c: scores.get(c.instrument.ticker, 0), reverse=True)
            return ranked[: self._max_candidates]
        except Exception:
            return candidates[: self._max_candidates]

    def _analyse_one(self, candidate: CandidateEvent) -> Recommendation | None:
        ticker = candidate.instrument.ticker
        price = self._prices.latest_close(ticker) or 0.0
        headlines = self._news.headlines(ticker, limit=15)
        filings = self._filings.summary(ticker, days=90)

        user_msg = build_analyst_prompt(candidate, price, headlines, filings)
        try:
            resp = self._llm.complete(_ANALYST_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            data = json.loads(_strip_fences(resp.content))
        except Exception:
            return None

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
                size_pct=0.02,
                confidence=float(data.get("confidence", 0.5)),
                catalyst=str(data.get("catalyst", candidate.evidence)),
                thesis=str(data.get("thesis", "")),
                horizon=str(data.get("horizon", "1-2 weeks")),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _challenge(self, rec: Recommendation) -> Recommendation | None:
        """Run the challenger pass. Returns adjusted/None recommendation."""
        if not self._budget.allow(_CHALLENGER_COST):
            return rec  # budget exhausted — skip challenger, keep rec

        ticker = rec.instrument.ticker
        headlines = self._news.headlines(ticker, limit=10) if self._news else []

        user_msg = build_challenger_prompt(
            ticker=ticker,
            entry=rec.entry,
            stop=rec.stop_loss or 0.0,
            target=rec.take_profit or 0.0,
            catalyst=rec.catalyst,
            thesis=rec.thesis,
            news=headlines,
        )
        try:
            resp = self._llm.complete(_CHALLENGER_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            data = json.loads(_strip_fences(resp.content))
        except Exception:
            return rec  # on parse failure keep original

        verdict = data.get("verdict", "pass")

        if verdict == "reject":
            return None

        if verdict == "weaken":
            adj = float(data.get("confidence_adjustment", -0.1))
            new_confidence = max(0.1, rec.confidence + adj)
            return Recommendation(
                instrument=rec.instrument,
                sleeve=rec.sleeve,
                side=rec.side,
                entry=rec.entry,
                stop_loss=rec.stop_loss,
                take_profit=rec.take_profit,
                size_pct=rec.size_pct,
                confidence=round(new_confidence, 3),
                catalyst=rec.catalyst,
                thesis=rec.thesis,
                horizon=rec.horizon,
            )

        return rec  # verdict == "pass"


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [l for l in lines[1:] if not l.startswith("```")]
        return "\n".join(inner)
    return text
