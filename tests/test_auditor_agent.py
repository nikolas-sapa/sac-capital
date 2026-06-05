"""Tests for the auditor agent (Stage 4) in the equity analyst pipeline."""
from __future__ import annotations

import json

import pytest

from core.assets.instrument import CapTier, Instrument
from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.analysis.prompt import build_auditor_prompt
from equities.strategy import Recommendation, Sleeve


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------

def test_build_auditor_prompt_contains_thesis_and_objections():
    result = build_auditor_prompt(
        thesis="Strong FCF growth + AI tailwind",
        objections=["Valuation stretched", "Insider selling"],
        catalyst="Earnings beat + raised guidance",
    )
    assert "Strong FCF growth" in result
    assert "Valuation stretched" in result
    assert "Insider selling" in result
    assert "Earnings beat" in result


def test_build_auditor_prompt_with_no_objections():
    result = build_auditor_prompt(
        thesis="Clear catalyst",
        objections=[],
        catalyst="FDA approval",
    )
    assert "(none)" in result


# ---------------------------------------------------------------------------
# _audit() integration tests
# ---------------------------------------------------------------------------

_INST = Instrument("KLIC", "Kulicke and Soffa", "NASDAQ", CapTier.MID)


def _make_recommendation(confidence: float = 0.72) -> Recommendation:
    return Recommendation(
        instrument=_INST,
        sleeve=Sleeve.SWING,
        side="buy",
        entry=50.0,
        stop_loss=46.0,
        take_profit=60.0,
        size_pct=0.02,
        confidence=confidence,
        catalyst="Earnings approaching",
        thesis="Supply chain bottleneck with pricing power",
        horizon="2-3 weeks",
    )


class _StubLLMAuditProceed:
    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({
                "bull_rigor": 0.8,
                "bear_rigor": 0.4,
                "consistency_penalty": 0.05,
                "fatal_flaw": None,
                "verdict": "proceed",
            }),
            input_tokens=200,
            output_tokens=80,
        )


class _StubLLMAuditReject:
    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({
                "bull_rigor": 0.2,
                "bear_rigor": 0.9,
                "consistency_penalty": 0.25,
                "fatal_flaw": "Catalyst already fully priced in",
                "verdict": "reject",
            }),
            input_tokens=200,
            output_tokens=80,
        )


def test_auditor_proceed_applies_consistency_penalty():
    analyst = EquityAnalyst(
        llm=_StubLLMAuditProceed(),
        budget=DailyBudget(daily_limit_usd=999.0),
    )
    rec = _make_recommendation(confidence=0.72)
    result = analyst._audit(rec, objections=["Valuation stretched"])
    assert result is not None
    assert result.confidence == round(0.72 - 0.05, 3)


def test_auditor_reject_returns_none():
    analyst = EquityAnalyst(
        llm=_StubLLMAuditReject(),
        budget=DailyBudget(daily_limit_usd=999.0),
    )
    rec = _make_recommendation(confidence=0.65)
    result = analyst._audit(rec, objections=["Stock already ran 40%"])
    assert result is None
