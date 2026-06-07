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
    _HAIKU = "fast"

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
            entry_price=float(position.get("entry_price", 0.0)),
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
