"""Core DCA analyst — risk-officer check before accumulating into quality large-caps.

Runs one Sonnet call per candidate. Returns a Recommendation with sleeve=CORE
and no stop/take_profit. Approves unless there is a specific near-term risk.
"""
from __future__ import annotations

import json

from equities.analysis.analyst import LLMClient, LLMResponse, _strip_fences
from equities.analysis.budget import DailyBudget
from equities.analysis.prompt import _CORE_DCA_SYSTEM, build_core_dca_prompt
from equities.screen.quality_screen import QualityCandidate
from equities.strategy import Recommendation, Sleeve

_SONNET = "claude-sonnet-4-6"
_CORE_DCA_COST = 0.008


class CoreDCAAnalyst:
    """Sonnet risk-officer pass for core DCA candidates.

    For each QualityCandidate:
      - Fetch recent news headlines
      - Ask Sonnet: any specific reason to wait?
      - "wait" → skip; "dca" → open a small position

    When `llm` is None, uses ClaudeCodeClient (Claude subscription).
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        prices=None,
        news=None,
        budget: DailyBudget | None = None,
        max_candidates: int = 4,
    ) -> None:
        if llm is None:
            from core.claude_client import ClaudeCodeClient
            llm = ClaudeCodeClient()  # type: ignore[assignment]
        self._llm = llm
        self._prices = prices
        self._news = news
        self._budget = budget or DailyBudget(daily_limit_usd=1.0)
        self._max_candidates = max_candidates

    def analyse(self, candidates: list[QualityCandidate]) -> list[Recommendation]:
        """Return DCA recommendations for approved candidates."""
        results: list[Recommendation] = []
        for candidate in candidates[: self._max_candidates]:
            if not self._budget.allow(_CORE_DCA_COST):
                break
            rec = self._analyse_one(candidate)
            if rec is not None:
                results.append(rec)
        return results

    def _analyse_one(self, candidate: QualityCandidate) -> Recommendation | None:
        ticker = candidate.instrument.ticker
        price = self._prices.latest_close(ticker) or 0.0 if self._prices else 0.0
        headlines = self._news.headlines(ticker, limit=15) if self._news else []

        user_msg = build_core_dca_prompt(candidate, price, headlines)
        try:
            resp = self._llm.complete(_CORE_DCA_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            data = json.loads(_strip_fences(resp.content))
        except Exception:
            return None

        if data.get("action") != "dca":
            return None

        dca_pct = float(data.get("dca_pct", 0.01))
        dca_pct = max(0.005, min(0.015, dca_pct))  # clamp to safe range

        return Recommendation(
            instrument=candidate.instrument,
            sleeve=Sleeve.CORE,
            side="buy",
            entry=price,
            stop_loss=None,
            take_profit=None,
            size_pct=dca_pct,
            confidence=candidate.score,
            catalyst="DCA accumulation — quality screen pass",
            thesis=str(data.get("thesis", "")),
            horizon="long-term",
        )
