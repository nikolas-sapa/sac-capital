"""Tests for sizing debate — challenger can push back on position size."""
import json
from datetime import date

import pytest

from core.assets.instrument import CapTier, Instrument
from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.analysis.schema import parse_challenger_decision
from equities.screen.event_screen import CandidateEvent, EventType
from equities.strategy import Recommendation, Sleeve


def _event(ticker: str = "TEST") -> CandidateEvent:
    return CandidateEvent(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        event_type=EventType.EARNINGS_APPROACHING,
        evidence="Earnings in 5d",
        urgency=0.8,
        days_to_event=5,
    )


def _rec(ticker: str = "TEST") -> Recommendation:
    """Build a test recommendation that passes through _challenge."""
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        size_pct=0.02,
        confidence=0.70,
        catalyst="Earnings in 5d",
        thesis="Strong growth profile with positive earnings surprise expected",
        horizon="1-2 weeks",
    )


class FakeLLMClient:
    """LLM client that returns fixed responses from a list."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        self.calls.append((model, user))
        content = self._responses.pop(0) if self._responses else '{"verdict": "pass"}'
        return LLMResponse(content=content, input_tokens=100, output_tokens=50)


class FakeNews:
    def headlines(self, ticker: str, limit: int = 8) -> list[str]:
        return []


# ============================================================================
# Test 1: Parser — ChallengerDecision with size_verdict and size_rationale
# ============================================================================

class TestSizingDebateParser:
    """Verify parser handles size_verdict in all cases."""

    def test_parse_full_verdict(self):
        """Challenger says full size is OK."""
        json_str = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "full",
            "size_rationale": "Vol regime normal, position sizing justified",
        })
        decision = parse_challenger_decision(json_str)
        assert decision.size_verdict == "full"
        assert decision.size_rationale == "Vol regime normal, position sizing justified"

    def test_parse_half_verdict(self):
        """Challenger says halve the position."""
        json_str = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "half",
            "size_rationale": "High vol environment, reduce to half size",
        })
        decision = parse_challenger_decision(json_str)
        assert decision.size_verdict == "half"
        assert decision.size_rationale == "High vol environment, reduce to half size"

    def test_parse_skip_verdict(self):
        """Challenger says skip the trade entirely."""
        json_str = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "skip",
            "size_rationale": "Earnings risk too high for this vol regime",
        })
        decision = parse_challenger_decision(json_str)
        assert decision.size_verdict == "skip"
        assert decision.size_rationale == "Earnings risk too high for this vol regime"

    def test_parse_absent_size_verdict_defaults_to_full(self):
        """When size_verdict is absent, default to 'full' for backward compat."""
        json_str = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
        })
        decision = parse_challenger_decision(json_str)
        assert decision.size_verdict == "full"
        assert decision.size_rationale == ""

    def test_parse_invalid_size_verdict_coerced_to_full(self):
        """Invalid size_verdict is coerced to 'full' (backward compat)."""
        json_str = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "maybe",
            "size_rationale": "Invalid verdict",
        })
        decision = parse_challenger_decision(json_str)
        assert decision.size_verdict == "full"

    def test_parse_size_verdict_uppercase_normalized(self):
        """Uppercase size_verdict is normalized to lowercase."""
        json_str = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "HALF",
            "size_rationale": "Test normalization",
        })
        decision = parse_challenger_decision(json_str)
        assert decision.size_verdict == "half"

    def test_parse_absent_size_rationale_defaults_to_empty(self):
        """When size_rationale is absent, default to empty string."""
        json_str = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "half",
        })
        decision = parse_challenger_decision(json_str)
        assert decision.size_rationale == ""


# ============================================================================
# Test 2: Wiring — Recommendation gets size_verdict from _challenge
# ============================================================================

class TestSizingDebateWiring:
    """Verify _challenge attaches size_verdict to Recommendation."""

    def test_challenge_full_verdict_on_recommendation(self):
        """_challenge returns rec with size_verdict='full'."""
        challenger_json = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "full",
            "size_rationale": "Normal sizing",
        })
        llm = FakeLLMClient([challenger_json])
        analyst = EquityAnalyst(
            llm=llm,
            news=FakeNews(),
            budget=DailyBudget(daily_limit_usd=100.0),
        )
        rec = _rec()
        challenged, _ = analyst._challenge(rec)
        assert challenged is not None
        assert hasattr(challenged, "size_verdict")
        assert challenged.size_verdict == "full"

    def test_challenge_half_verdict_on_recommendation(self):
        """_challenge returns rec with size_verdict='half'."""
        challenger_json = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "half",
            "size_rationale": "Reduce for high vol",
        })
        llm = FakeLLMClient([challenger_json])
        analyst = EquityAnalyst(
            llm=llm,
            news=FakeNews(),
            budget=DailyBudget(daily_limit_usd=100.0),
        )
        rec = _rec()
        challenged, _ = analyst._challenge(rec)
        assert challenged is not None
        assert challenged.size_verdict == "half"
        assert challenged.size_rationale == "Reduce for high vol"

    def test_challenge_skip_verdict_on_recommendation(self):
        """_challenge returns rec with size_verdict='skip'."""
        challenger_json = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
            "size_verdict": "skip",
            "size_rationale": "Too much thesis risk",
        })
        llm = FakeLLMClient([challenger_json])
        analyst = EquityAnalyst(
            llm=llm,
            news=FakeNews(),
            budget=DailyBudget(daily_limit_usd=100.0),
        )
        rec = _rec()
        challenged, _ = analyst._challenge(rec)
        assert challenged is not None
        assert challenged.size_verdict == "skip"

    def test_challenge_absent_size_verdict_defaults_on_recommendation(self):
        """_challenge with absent size_verdict defaults rec to 'full'."""
        challenger_json = json.dumps({
            "verdict": "pass",
            "objections": [],
            "confidence_adjustment": 0.0,
        })
        llm = FakeLLMClient([challenger_json])
        analyst = EquityAnalyst(
            llm=llm,
            news=FakeNews(),
            budget=DailyBudget(daily_limit_usd=100.0),
        )
        rec = _rec()
        challenged, _ = analyst._challenge(rec)
        assert challenged is not None
        assert challenged.size_verdict == "full"

    def test_challenge_weaken_preserves_size_verdict(self):
        """_challenge with 'weaken' verdict preserves size_verdict."""
        challenger_json = json.dumps({
            "verdict": "weaken",
            "objections": ["Some concern"],
            "confidence_adjustment": -0.1,
            "size_verdict": "half",
            "size_rationale": "Concern warrants half sizing",
        })
        llm = FakeLLMClient([challenger_json])
        analyst = EquityAnalyst(
            llm=llm,
            news=FakeNews(),
            budget=DailyBudget(daily_limit_usd=100.0),
        )
        rec = _rec()
        challenged, _ = analyst._challenge(rec)
        assert challenged is not None
        assert challenged.size_verdict == "half"


# ============================================================================
# Helper function (used by runner)
# ============================================================================

def apply_sizing_verdict(rec: Recommendation) -> tuple[Recommendation, str]:
    """Apply size_verdict to recommendation, return (adjusted_rec, decision).

    decision: "proceed" for "full"/"half", "skip" for "skip"
    """
    from dataclasses import replace as dc_replace

    verdict = getattr(rec, "size_verdict", "full")
    if verdict == "skip":
        return rec, "skip"

    if verdict == "half":
        # Halve the size_pct
        rec_halved = dc_replace(rec, size_pct=rec.size_pct * 0.5)
        return rec_halved, "proceed"

    return rec, "proceed"


# ============================================================================
# Test 3: apply_sizing_verdict helper
# ============================================================================


class TestApplySizingVerdict:
    """Verify apply_sizing_verdict helper function."""

    def test_full_verdict_proceeds_unchanged(self):
        """'full' verdict → proceed, size_pct unchanged."""
        from dataclasses import replace as dc_replace
        rec = _rec()
        rec = dc_replace(rec, size_verdict="full")
        rec_out, decision = apply_sizing_verdict(rec)
        assert decision == "proceed"
        assert rec_out.size_pct == 0.02

    def test_half_verdict_proceeds_halved(self):
        """'half' verdict → proceed, size_pct halved."""
        from dataclasses import replace as dc_replace
        rec = _rec()
        rec = dc_replace(rec, size_verdict="half")
        rec_out, decision = apply_sizing_verdict(rec)
        assert decision == "proceed"
        assert rec_out.size_pct == 0.01

    def test_skip_verdict_skips(self):
        """'skip' verdict → skip, recommendation unchanged."""
        from dataclasses import replace as dc_replace
        rec = _rec()
        rec = dc_replace(rec, size_verdict="skip")
        rec_out, decision = apply_sizing_verdict(rec)
        assert decision == "skip"
        assert rec_out is rec  # Unchanged

    def test_absent_verdict_defaults_to_full(self):
        """Absent size_verdict → proceed, size_pct unchanged."""
        rec = _rec()
        # Don't set size_verdict; getattr should default to "full"
        rec_out, decision = apply_sizing_verdict(rec)
        assert decision == "proceed"
        assert rec_out.size_pct == 0.02
