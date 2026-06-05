"""Tests for ThesisHealthChecker."""
from __future__ import annotations

import json

from equities.analysis.analyst import LLMResponse
from equities.killgate.thesis_health import ThesisHealth, ThesisHealthChecker


class _LLM:
    def __init__(self, status: str, action: str, reason: str) -> None:
        self._d = {"status": status, "action": action, "reason": reason}

    def complete(self, s: str, u: str, m: str) -> LLMResponse:
        return LLMResponse(content=json.dumps(self._d), input_tokens=200, output_tokens=80)


_POS = {
    "id": "p1",
    "ticker": "KLIC",
    "thesis": "Bottleneck play",
    "catalyst": "Earnings",
    "entry_price": 50.0,
    "sleeve": "swing",
}


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
