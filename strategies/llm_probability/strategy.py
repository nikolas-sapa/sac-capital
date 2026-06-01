from __future__ import annotations

from core.markets import Market
from core.strategy import Signal
from strategies.llm_probability.budget import DailyBudget
from strategies.llm_probability.llm import LLMClient
from strategies.llm_probability.prompt import build_prompt

_DEFAULT_MIN_EDGE = 0.08
_DEFAULT_MIN_CONF = 0.55
_DEFAULT_RESOLUTION_TEXT = "Resolves according to Polymarket resolution source."


def _default_client() -> LLMClient:
    """Build a ClaudeCodeBackend-backed LLMClient (uses Claude subscription)."""
    from core.claude_client import ClaudeCodeBackend
    return LLMClient(backend=ClaudeCodeBackend(), budget=DailyBudget(limit_usd=999.0))


class LLMProbabilityStrategy:
    """Scan thin/illiquid Polymarket markets; emit Signals where Claude's
    estimated edge clears both the min_edge and min_conf thresholds.

    When called with no arguments, uses ClaudeCodeBackend (your Claude
    subscription via `claude -p`) — no API key required.
    """

    name = "llm_probability"

    def __init__(
        self,
        client=None,  # LLMClient or any duck-typed stub; defaults to ClaudeCodeBackend
        min_edge: float = _DEFAULT_MIN_EDGE,
        min_conf: float = _DEFAULT_MIN_CONF,
        resolution_text: str = _DEFAULT_RESOLUTION_TEXT,
    ) -> None:
        self._client = client if client is not None else _default_client()
        self._min_edge = min_edge
        self._min_conf = min_conf
        self._resolution_text = resolution_text

    def scan(self, markets: list[Market]) -> list[Signal]:
        candidates = self._client.prefilter(markets)
        signals: list[Signal] = []

        for market in candidates:
            yes_outcomes = [o for o in market.outcomes if o.label.lower() == "yes"]
            if not yes_outcomes:
                continue
            yes = yes_outcomes[0]
            prompt = build_prompt(market, self._resolution_text)

            try:
                est = self._client.estimate_probability(prompt)
            except (RuntimeError, ValueError):
                continue

            edge = est.probability - yes.best_ask
            if edge >= self._min_edge and est.confidence >= self._min_conf:
                signals.append(
                    Signal(
                        market=market,
                        token_id=yes.token_id,
                        fair_prob=est.probability,
                        price=yes.best_ask,
                        confidence=est.confidence,
                        reason=est.reasoning,
                    )
                )

        return signals
