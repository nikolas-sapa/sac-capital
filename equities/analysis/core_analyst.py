"""Core DCA analyst — risk-officer check before accumulating into quality large-caps.

Runs one Sonnet call per candidate. Returns a Recommendation with sleeve=CORE
and no stop/take_profit. Approves unless there is a specific near-term risk.
"""
from __future__ import annotations

import math
import os

from equities.analysis.analyst import LLMClient, LLMResponse, LLMFailureBudgetExceeded
from equities.analysis.budget import DailyBudget
from equities.analysis.core_reviewers import (
    format_core_reviews,
    has_hard_reject,
    run_core_reviewers,
)
from equities.analysis.prompt import _CORE_DCA_SYSTEM, build_core_dca_prompt
from equities.analysis.schema import parse_core_dca_decision
from equities.data.fundamentals import FundamentalsProvider
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

    When `llm` is None, uses OpenAI if OPENAI_API_KEY is set, otherwise Claude
    CLI fallback.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        prices=None,
        news=None,
        fundamentals: FundamentalsProvider | None = None,
        budget: DailyBudget | None = None,
        max_candidates: int = 4,
        reviewers_enabled: bool | None = None,
    ) -> None:
        if llm is None:
            from core.claude_client import ClaudeCodeClient
            llm = ClaudeCodeClient()  # type: ignore[assignment]
        self._llm = llm
        self._prices = prices
        self._news = news
        self._fundamentals = fundamentals
        self._budget = budget or DailyBudget(daily_limit_usd=1.0)
        self._max_candidates = max_candidates
        if reviewers_enabled is None:
            reviewers_enabled = os.getenv("EQUITY_CORE_REVIEWERS_ENABLED", "true").lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        self._reviewers_enabled = reviewers_enabled

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
        if not self._prices:
            print(f"  REJECTED [{ticker}] core_market_data_missing: no_price_provider")
            return None
        price = self._prices.latest_close(ticker)
        if price is None or not math.isfinite(price) or price <= 0:
            print(f"  REJECTED [{ticker}] core_market_data_invalid: latest_close={price!r}")
            return None
        headlines = self._news.headlines(ticker, limit=15) if self._news else []
        reviewer_block = self._reviewer_block(candidate)
        if reviewer_block is None:
            print(f"  REJECTED [{ticker}] core_reviewer_hard_reject")
            return None

        user_msg = build_core_dca_prompt(candidate, price, headlines, reviewer_block=reviewer_block)
        try:
            resp = self._llm.complete(_CORE_DCA_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            data = parse_core_dca_decision(resp.content)
        except LLMFailureBudgetExceeded:
            raise
        except Exception:
            return None

        if data.action != "dca":
            return None

        dca_pct = float(data.dca_pct or 0.01)
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
            thesis=data.thesis,
            horizon="long-term",
            memo={"core_reviewer_checks": reviewer_block} if reviewer_block else None,
        )

    def _reviewer_block(self, candidate: QualityCandidate) -> str | None:
        if not self._reviewers_enabled or self._fundamentals is None:
            return ""
        try:
            snap = self._fundamentals.fetch(candidate.instrument.ticker)
            reviews = run_core_reviewers(snap)
        except Exception:
            return ""
        if has_hard_reject(reviews):
            return None
        return format_core_reviews(reviews)
