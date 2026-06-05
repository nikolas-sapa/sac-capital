"""Tests for the challenger pass in EquityAnalyst."""
from __future__ import annotations

import json
import pytest

from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.screen.event_screen import CandidateEvent
from equities.strategy import Recommendation, Sleeve
from core.assets.instrument import CapTier, Instrument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INST = Instrument("TEST", "Test Corp", "NASDAQ", CapTier.MID)


def _rec(confidence: float = 0.7) -> Recommendation:
    return Recommendation(
        instrument=_INST,
        sleeve=Sleeve.SWING,
        side="buy",
        entry=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        size_pct=0.02,
        confidence=confidence,
        catalyst="earnings beat",
        thesis="market has not priced in ARR acceleration",
        horizon="1-2 weeks",
    )


class _StubLLM:
    """Returns scripted responses in sequence."""
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        content = next(self._responses)
        return LLMResponse(content=content, input_tokens=100, output_tokens=50)


def _make_analyst(llm_responses: list[str]) -> EquityAnalyst:
    analyst = EquityAnalyst.__new__(EquityAnalyst)
    analyst._llm = _StubLLM(llm_responses)
    analyst._prices = None
    analyst._news = None
    analyst._filings = None
    analyst._budget = DailyBudget(daily_limit_usd=999.0)
    analyst._max_candidates = 5
    return analyst


# ---------------------------------------------------------------------------
# Challenger tests
# ---------------------------------------------------------------------------

def test_challenger_pass_keeps_recommendation():
    verdict = json.dumps({
        "verdict": "pass",
        "objections": [],
        "confidence_adjustment": 0.0,
        "summary": "no issues",
    })
    analyst = _make_analyst([verdict])
    result, objections = analyst._challenge(_rec(0.7))
    assert result is not None
    assert result.confidence == pytest.approx(0.7)
    assert objections == []


def test_challenger_reject_drops_recommendation():
    verdict = json.dumps({
        "verdict": "reject",
        "objections": ["catalyst already priced in — stock up 18% since filing"],
        "confidence_adjustment": -0.3,
        "summary": "re-rating complete",
    })
    analyst = _make_analyst([verdict])
    result, objections = analyst._challenge(_rec(0.7))
    assert result is None
    assert len(objections) == 1


def test_challenger_weaken_reduces_confidence():
    verdict = json.dumps({
        "verdict": "weaken",
        "objections": ["high short interest may cause squeeze volatility"],
        "confidence_adjustment": -0.15,
        "summary": "proceed with lower size",
    })
    analyst = _make_analyst([verdict])
    result, objections = analyst._challenge(_rec(0.7))
    assert result is not None
    assert result.confidence == pytest.approx(0.55, abs=0.01)
    assert len(objections) == 1


def test_challenger_weaken_floors_confidence_at_0_1():
    verdict = json.dumps({
        "verdict": "weaken",
        "objections": ["very weak thesis"],
        "confidence_adjustment": -0.9,
        "summary": "barely pass",
    })
    analyst = _make_analyst([verdict])
    result, _ = analyst._challenge(_rec(0.2))
    assert result is not None
    assert result.confidence >= 0.1


def test_challenger_skipped_on_budget_exhausted():
    analyst = _make_analyst([])
    analyst._budget = DailyBudget(daily_limit_usd=0.0)
    rec = _rec(0.7)
    result, objections = analyst._challenge(rec)
    assert result is rec  # returned unchanged
    assert objections == []


def test_challenger_parse_error_keeps_recommendation():
    analyst = _make_analyst(["NOT VALID JSON )))"])
    result, objections = analyst._challenge(_rec(0.7))
    assert result is not None
    assert result.confidence == pytest.approx(0.7)
    assert objections == []
