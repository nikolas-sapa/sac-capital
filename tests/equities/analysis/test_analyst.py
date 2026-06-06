"""Tests for EquityAnalyst — uses a fake LLM client."""
import json
from datetime import date, timedelta

import pytest

from core.assets.instrument import CapTier, Instrument
from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.analysis.core_analyst import CoreDCAAnalyst
from equities.research.artifacts import EquityResearchArtifact, stable_hash
from equities.research.store import ResearchArtifactStore
from equities.screen.event_screen import CandidateEvent, EventType
from equities.screen.quality_screen import QualityCandidate
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
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        self.calls.append((model, user))
        content = self._responses.get(model, '{"action": "reject", "reason": "test"}')
        return LLMResponse(content=content, input_tokens=100, output_tokens=50)


class SequenceLLMClient:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        self.calls.append((model, user))
        content = self._responses.pop(0)
        return LLMResponse(content=content, input_tokens=100, output_tokens=50)


class FakePrices:
    def latest_close(self, ticker: str) -> float | None:
        return 74.36

    def latest_bar(self, ticker: str):
        class Bar:
            day = date.today()

        return Bar()


class FakeCorePrice:
    def latest_close(self, ticker: str) -> float | None:
        return 100.0


class PriceCase:
    def __init__(self, close, day=date.today()):
        self.close = close
        self.day = day

    def latest_close(self, ticker: str):
        return self.close

    def latest_bar(self, ticker: str):
        class Bar:
            pass

        bar = Bar()
        bar.day = self.day
        return bar


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
    "business_quality": "Gross margins are high and revenue growth remains above peer median.",
    "valuation": "Entry is below the prior post-data high and assumes no full pipeline credit.",
    "balance_sheet_risk": "Cash runway appears adequate for the catalyst window.",
    "market_expectation_gap": "Recent coverage still frames the event as binary rather than platform-validating.",
    "invalidation": "Reject if the FDA update is delayed or price closes below the stop.",
    "evidence_citations": ["Current price: $74.36", "8-K item 2.02 filed 3d ago", "headline 1"],
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
    assert rec.memo is not None
    assert rec.memo["business_quality"]
    assert rec.memo["evidence_citations"]


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


@pytest.mark.parametrize("close", [None, 0.0, float("nan")])
def test_analyst_rejects_invalid_price_before_deep_prompt(close):
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_BUY_RESPONSE})
    analyst = EquityAnalyst(llm, PriceCase(close), FakeNews(), FakeFilings())

    results = analyst.analyse([_event("ARWR")])

    assert results == []
    assert all("Current price: $0.00" not in user for _, user in llm.calls)
    assert [model for model, _ in llm.calls].count(_SONNET) == 0


def test_analyst_rejects_stale_price_before_deep_prompt():
    old_day = date.today() - timedelta(days=30)
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_BUY_RESPONSE})
    analyst = EquityAnalyst(
        llm,
        PriceCase(74.36, old_day),
        FakeNews(),
        FakeFilings(),
        max_price_age_days=7,
    )

    results = analyst.analyse([_event("ARWR")])

    assert results == []
    assert [model for model, _ in llm.calls].count(_SONNET) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"entry": 74.0, "stop_loss": 75.0, "take_profit": 88.0, "confidence": 0.7},
        {"entry": 74.0, "stop_loss": 68.0, "take_profit": 70.0, "confidence": 0.7},
        {"entry": 0.0, "stop_loss": 68.0, "take_profit": 88.0, "confidence": 0.7},
        {"entry": 74.0, "stop_loss": 68.0, "take_profit": 88.0, "confidence": 1.7},
    ],
)
def test_analyst_rejects_invalid_buy_schema(payload):
    data = {
        "action": "buy",
        "horizon": "2-3 weeks",
        "catalyst": "Plozasiran FDA data due",
        "thesis": "Market underestimates the cardiometabolic pipeline.",
        "business_quality": "Gross margins are high and revenue growth remains above peer median.",
        "valuation": "Entry is below the prior post-data high and assumes no full pipeline credit.",
        "balance_sheet_risk": "Cash runway appears adequate for the catalyst window.",
        "market_expectation_gap": "Recent coverage still frames the event as binary rather than platform-validating.",
        "invalidation": "Reject if the FDA update is delayed or price closes below the stop.",
        "evidence_citations": ["Current price: $74.36"],
        **payload,
    }
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: json.dumps(data)})
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings())

    assert analyst.analyse([_event("ARWR")]) == []


def test_analyst_rejects_buy_without_structured_memo():
    data = {
        "action": "buy",
        "entry": 74.0,
        "stop_loss": 68.0,
        "take_profit": 88.0,
        "confidence": 0.72,
        "horizon": "2-3 weeks",
        "catalyst": "Plozasiran FDA data due",
        "thesis": "Market underestimates the cardiometabolic pipeline.",
    }
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: json.dumps(data)})
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings())

    assert analyst.analyse([_event("ARWR")]) == []


def test_analyst_accepts_fenced_json():
    llm = FakeLLMClient({
        _HAIKU: _PREFILTER_RESPONSE,
        _SONNET: "```json\n" + _SONNET_BUY_RESPONSE + "\n```",
    })
    analyst = EquityAnalyst(llm, FakePrices(), FakeNews(), FakeFilings())

    results = analyst.analyse([_event("ARWR")])

    assert len(results) == 1


def test_analyst_writes_research_artifacts_for_accept_and_reject(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_BUY_RESPONSE})
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        artifact_store=store,
    )
    assert len(analyst.analyse([_event("ARWR")])) == 1

    reject_llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_REJECT_RESPONSE})
    rejecting_analyst = EquityAnalyst(
        reject_llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        artifact_store=store,
    )
    assert rejecting_analyst.analyse([_event("ARWR")]) == []

    artifacts = store.read_all()
    assert [artifact.decision for artifact in artifacts] == ["approved", "approved", "rejected"]
    assert artifacts[0].ticker == "ARWR"
    assert artifacts[0].prompt_hash
    assert artifacts[0].sources
    assert artifacts[2].rejection_reason


def test_analyst_includes_existing_same_ticker_memory_in_prompt(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    store.append(
        EquityResearchArtifact(
            artifact_id=stable_hash({"ticker": "ARWR", "case": "memory"}),
            as_of="2026-01-01T00:00:00+00:00",
            ticker="ARWR",
            candidate={"ticker": "ARWR", "evidence": "Prior earnings setup"},
            output_json={
                "action": "buy",
                "entry": 70.0,
                "stop_loss": 65.0,
                "take_profit": 84.0,
                "confidence": 0.66,
                "catalyst": "Prior accepted catalyst from artifacts",
                "thesis": "Prior thesis",
            },
            decision="approved",
        )
    )
    llm = FakeLLMClient({_HAIKU: _PREFILTER_RESPONSE, _SONNET: _SONNET_BUY_RESPONSE})
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        artifact_store=store,
    )

    analyst.analyse([_event("ARWR")])

    analyst_prompts = [
        user for model, user in llm.calls
        if model == _SONNET and "Analyze this equity catalyst." in user
    ]
    assert analyst_prompts
    assert "## Decision memory" in analyst_prompts[0]
    assert "Prior accepted catalyst from artifacts" in analyst_prompts[0]


def test_invalid_challenger_output_is_artifacted_and_trade_continues(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    llm = SequenceLLMClient([
        _PREFILTER_RESPONSE,
        _SONNET_BUY_RESPONSE,
        '{"verdict": "weaken", "confidence_adjustment": 0.2}',
        '{"verdict": "pass", "consistency_penalty": 0.0}',
    ])
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        artifact_store=store,
    )

    results = analyst.analyse([_event("ARWR")])

    assert len(results) == 1
    artifacts = store.read_all()
    challenger_errors = [
        artifact for artifact in artifacts
        if artifact.extractions[0].provider == "equity_challenger"
    ]
    assert challenger_errors
    assert challenger_errors[0].decision == "error"
    assert "challenger_output_invalid" in challenger_errors[0].rejection_reason


def test_invalid_auditor_output_is_artifacted_and_trade_continues(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    llm = SequenceLLMClient([
        _PREFILTER_RESPONSE,
        _SONNET_BUY_RESPONSE,
        '{"verdict": "pass", "objections": []}',
        '{"verdict": "pass", "consistency_penalty": -0.1}',
    ])
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        artifact_store=store,
    )

    results = analyst.analyse([_event("ARWR")])

    assert len(results) == 1
    artifacts = store.read_all()
    auditor_errors = [
        artifact for artifact in artifacts
        if artifact.extractions[0].provider == "equity_auditor"
    ]
    assert auditor_errors
    assert auditor_errors[0].decision == "error"
    assert "auditor_output_invalid" in auditor_errors[0].rejection_reason


def test_core_dca_rejects_invalid_output():
    llm = FakeLLMClient({_SONNET: '{"action": "dca", "dca_pct": 0.01}'})
    candidate = QualityCandidate(
        instrument=Instrument("MSFT", "Microsoft", "NASDAQ", CapTier.LARGE),
        score=0.8,
        evidence="quality",
    )
    analyst = CoreDCAAnalyst(llm, FakeCorePrice(), FakeNews())

    assert analyst.analyse([candidate]) == []
