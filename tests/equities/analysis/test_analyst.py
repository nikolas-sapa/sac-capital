"""Tests for EquityAnalyst — uses a fake LLM client."""
import json
from datetime import date, timedelta

import pytest

from core.assets.instrument import CapTier, Instrument
from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.screen.event_screen import CandidateEvent, EventType
from equities.strategy import Recommendation


def _event(ticker: str = "ARWR") -> CandidateEvent:
    return CandidateEvent(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        event_type=EventType.EARNINGS_APPROACHING,
        evidence="Earnings in 5d",
        urgency=0.8,
        days_to_event=5,
    )


class FakeLLMClient:
    def __init__(self, responses: dict[str, str]):
        self._responses = responses  # model → json string

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        content = self._responses.get(model, '{"action": "reject", "reason": "test"}')
        return LLMResponse(content=content, input_tokens=100, output_tokens=50)


class FakePrices:
    def latest_close(self, ticker: str) -> float | None:
        return 74.36


class FakeNews:
    def headlines(self, ticker: str, limit: int = 8) -> list[str]:
        return ["headline 1", "headline 2"]


class FakeFilings:
    def summary(self, ticker: str, days: int = 90) -> list[str]:
        return ["8-K item 2.02 filed 3d ago"]


_HAIKU = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"

_PREFILTER_RESPONSE = json.dumps({
    "rankings": [{"ticker": "ARWR", "score": 8, "reason": "strong catalyst"}]
})

_SONNET_BUY_RESPONSE = json.dumps({
    "action": "buy",
    "entry": 74.0,
    "stop_loss": 68.0,
    "take_profit": 88.0,
    "confidence": 0.72,
    "horizon": "2-3 weeks",
    "catalyst": "Plozasiran FDA data due",
    "thesis": "Market underestimates the cardiometabolic pipeline.",
})

_SONNET_REJECT_RESPONSE = json.dumps({
    "action": "reject",
    "reason": "re-rating already complete, stock up 18% since 8-K",
})


def test_analyst_returns_recommendation_on_buy():
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_BUY_RESPONSE})
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings())
    results = analyst.analyse([_event("ARWR")])
    assert len(results) == 1
    rec = results[0]
    assert isinstance(rec, Recommendation)
    assert rec.entry == pytest.approx(74.0)
    assert rec.stop_loss == pytest.approx(68.0)
    assert rec.take_profit == pytest.approx(88.0)


def test_analyst_rejects_already_priced_in():
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_REJECT_RESPONSE})
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings())
    results = analyst.analyse([_event("ARWR")])
    assert results == []


def test_analyst_respects_budget():
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_BUY_RESPONSE})
    budget = DailyBudget(daily_limit_usd=0.0)  # exhausted
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings(), budget=budget)
    results = analyst.analyse([_event("ARWR")])
    assert results == []


def test_analyst_empty_candidates():
    llm = FakeLLMClient({})
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings())
    assert analyst.analyse([]) == []


def test_analyst_handles_bad_json_gracefully():
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: "not json at all"})
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings())
    results = analyst.analyse([_event("ARWR")])
    assert results == []


def test_analyst_handles_bad_prefilter_json_gracefully():
    # If Haiku returns garbage, fall back to first N by urgency
    llm = FakeLLMClient({_HAIKU: "{{bad json}}", _SONNET: _SONNET_BUY_RESPONSE})
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings(), max_candidates=3)
    results = analyst.analyse([_event("A"), _event("B")])
    assert len(results) <= 2  # no crash
