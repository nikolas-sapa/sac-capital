from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from core.markets import Market
from strategies.llm_probability.budget import DailyBudget
from strategies.llm_probability.filters import candidate_markets
from strategies.llm_probability.prompt import build_prompt, SYSTEM_PROMPT

# Rough cost estimates (USD per call) for budget guard
_HAIKU_COST_EST = 0.001
_SONNET_COST_EST = 0.01


@dataclass(frozen=True)
class ProbEstimate:
    probability: float
    confidence: float
    reasoning: str


class _Backend(Protocol):
    def complete(self, prompt: str, *, model: str) -> str: ...
    def complete_batch(self, prompts: list[str], *, model: str) -> list[str]: ...


def _parse_estimate(raw: str) -> ProbEstimate:
    """Parse JSON response into ProbEstimate; raise ValueError on bad input."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"parse error: {exc}") from exc

    prob = float(data.get("probability", -1))
    if not (0.0 <= prob <= 1.0):
        raise ValueError(f"probability out of range: {prob}")

    return ProbEstimate(
        probability=prob,
        confidence=float(data.get("confidence", 0.5)),
        reasoning=str(data.get("reasoning", "")),
    )


class LLMClient:
    """Two-stage (Haiku pre-filter → Sonnet deep estimate) client.

    Inject a _Backend for tests; wire a real anthropic.Anthropic adapter for live use.
    """

    def __init__(self, backend: _Backend, budget: DailyBudget) -> None:
        self._backend = backend
        self._budget = budget

    def estimate_probability(self, prompt: str) -> ProbEstimate:
        """Call Sonnet for a calibrated estimate. Retries once on bad JSON."""
        if not self._budget.allow(_SONNET_COST_EST):
            raise RuntimeError("budget exhausted for today")

        raw = self._backend.complete(prompt, model="sonnet")
        self._budget.record(_SONNET_COST_EST)

        try:
            return _parse_estimate(raw)
        except ValueError:
            # One retry
            if not self._budget.allow(_SONNET_COST_EST):
                raise ValueError("parse error and budget exhausted on retry")
            raw2 = self._backend.complete(prompt, model="sonnet")
            self._budget.record(_SONNET_COST_EST)
            return _parse_estimate(raw2)

    def prefilter(self, markets: list[Market], max_candidates: int = 10) -> list[Market]:
        """Haiku pass: score markets cheaply and return the top candidates."""
        candidates = candidate_markets(markets)[:max_candidates]
        if not candidates:
            return []

        scored: list[tuple[float, Market]] = []
        for m in candidates:
            if not self._budget.allow(_HAIKU_COST_EST):
                break
            prompt = (
                f"Rate this prediction market 1-10 for how much LLM analysis could add edge. "
                f"Question: {m.question}. "
                f"Return ONLY a JSON object: {{\"score\": <int 1-10>}}"
            )
            raw = self._backend.complete(prompt, model="haiku")
            self._budget.record(_HAIKU_COST_EST)
            try:
                score = float(json.loads(raw).get("score", 5))
            except (json.JSONDecodeError, TypeError, ValueError):
                score = 5.0
            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored]
