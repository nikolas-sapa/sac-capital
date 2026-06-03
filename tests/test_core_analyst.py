"""Tests for CoreDCAAnalyst."""
from __future__ import annotations

import json
import pytest

from equities.analysis.analyst import LLMResponse
from equities.analysis.budget import DailyBudget
from equities.analysis.core_analyst import CoreDCAAnalyst
from equities.screen.quality_screen import QualityCandidate
from equities.strategy import Sleeve
from core.assets.instrument import CapTier, Instrument


_INST = Instrument("META", "Meta Platforms", "NASDAQ", CapTier.LARGE)


def _candidate(score: float = 0.78) -> QualityCandidate:
    return QualityCandidate(
        instrument=_INST,
        score=score,
        evidence="gross_margins=82%  |  trailing_pe=21.8  |  rev_growth=+33%",
    )


class _StubLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(content=self._response, input_tokens=100, output_tokens=50)


class _StubPrices:
    def latest_close(self, ticker: str) -> float | None:
        return 550.0


class _StubNews:
    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        return ["Meta Q1 beats estimates", "AI ad revenue accelerates"]


def _make_dca_analyst(llm_response: str) -> CoreDCAAnalyst:
    return CoreDCAAnalyst(
        llm=_StubLLM(llm_response),
        prices=_StubPrices(),
        news=_StubNews(),
        budget=DailyBudget(daily_limit_usd=999.0),
        max_candidates=4,
    )


def test_dca_approved_opens_core_position():
    resp = json.dumps({
        "action": "dca",
        "risk_flags": [],
        "dca_pct": 0.01,
        "thesis": "Strong fundamentals, no near-term risks",
    })
    results = _make_dca_analyst(resp).analyse([_candidate()])
    assert len(results) == 1
    rec = results[0]
    assert rec.sleeve == Sleeve.CORE
    assert rec.stop_loss is None
    assert rec.take_profit is None
    assert rec.side == "buy"
    assert rec.entry == pytest.approx(550.0)
    assert rec.size_pct == pytest.approx(0.01)


def test_dca_wait_skips_candidate():
    resp = json.dumps({
        "action": "wait",
        "risk_flags": ["CFO departure announced today"],
        "dca_pct": 0.01,
        "thesis": "Wait for leadership clarity",
    })
    assert _make_dca_analyst(resp).analyse([_candidate()]) == []


def test_dca_pct_clamped_upper_bound():
    resp = json.dumps({"action": "dca", "risk_flags": [], "dca_pct": 0.99, "thesis": "ok"})
    results = _make_dca_analyst(resp).analyse([_candidate()])
    assert results[0].size_pct == pytest.approx(0.015)


def test_dca_pct_clamped_lower_bound():
    resp = json.dumps({"action": "dca", "risk_flags": [], "dca_pct": 0.001, "thesis": "ok"})
    results = _make_dca_analyst(resp).analyse([_candidate()])
    assert results[0].size_pct == pytest.approx(0.005)


def test_dca_parse_error_skips():
    assert _make_dca_analyst("INVALID JSON").analyse([_candidate()]) == []


def test_dca_max_candidates_limit():
    resp = json.dumps({"action": "dca", "risk_flags": [], "dca_pct": 0.01, "thesis": "ok"})
    analyst = CoreDCAAnalyst(
        llm=_StubLLM(resp),
        prices=_StubPrices(),
        news=_StubNews(),
        budget=DailyBudget(daily_limit_usd=999.0),
        max_candidates=2,
    )
    results = analyst.analyse([_candidate() for _ in range(5)])
    assert len(results) <= 2


def test_dca_budget_exhausted_returns_empty():
    resp = json.dumps({"action": "dca", "risk_flags": [], "dca_pct": 0.01, "thesis": "ok"})
    analyst = CoreDCAAnalyst(
        llm=_StubLLM(resp),
        prices=_StubPrices(),
        news=_StubNews(),
        budget=DailyBudget(daily_limit_usd=0.0),
    )
    assert analyst.analyse([_candidate()]) == []
