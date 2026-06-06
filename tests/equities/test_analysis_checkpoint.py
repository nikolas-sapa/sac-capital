from __future__ import annotations

import json
from datetime import date

import pytest

from core.assets.instrument import CapTier, Instrument
from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.analysis.checkpoint import (
    AnalysisCheckpoint,
    AnalysisCheckpointStore,
    checkpoint_key,
    utc_now_iso,
)
from equities.analysis.prompt import build_analyst_prompt
from equities.research.artifacts import stable_hash
from equities.screen.event_screen import CandidateEvent, EventType


def _event(ticker: str = "ARWR", evidence: str = "Earnings in 5d") -> CandidateEvent:
    return CandidateEvent(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        event_type=EventType.EARNINGS_APPROACHING,
        evidence=evidence,
        urgency=0.8,
        days_to_event=5,
    )


class SequenceLLMClient:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        self.calls.append((model, user))
        return LLMResponse(
            content=self._responses.pop(0),
            input_tokens=100,
            output_tokens=50,
        )


class FakePrices:
    def latest_close(self, ticker: str) -> float | None:
        return 74.36

    def latest_bar(self, ticker: str):
        class Bar:
            day = date.today()

        return Bar()


class FakeNews:
    def headlines(self, ticker: str, limit: int = 8) -> list[str]:
        return ["headline 1", "headline 2"]


class FakeFilings:
    def summary(self, ticker: str, days: int = 90) -> list[str]:
        return ["8-K item 2.02 filed 3d ago"]


_PREFILTER_RESPONSE = json.dumps({
    "rankings": [{"ticker": "ARWR", "score": 8, "reason": "strong catalyst"}]
})

_BUY_RESPONSE = json.dumps({
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
    "market_expectation_gap": "Coverage still frames the event as binary.",
    "invalidation": "Reject if the FDA update is delayed or price closes below the stop.",
    "evidence_citations": ["Current price: $74.36", "headline 1"],
})

_CHALLENGER_RESPONSE = json.dumps({
    "verdict": "pass",
    "objections": [],
    "confidence_adjustment": 0.0,
    "summary": "pass",
})

_AUDITOR_RESPONSE = json.dumps({
    "bull_rigor": 0.8,
    "bear_rigor": 0.6,
    "consistency_penalty": 0.0,
    "fatal_flaw": None,
    "verdict": "proceed",
})


def test_checkpoint_store_get_put_clear_and_ignores_malformed_rows(tmp_path):
    path = tmp_path / "checkpoints.jsonl"
    store = AnalysisCheckpointStore(path)
    checkpoint = AnalysisCheckpoint(
        key="k1",
        ticker="ARWR",
        stage="analyst",
        model="claude-sonnet-4-6",
        prompt_hash="p1",
        raw_output='{"action":"reject","reason":"test"}',
        parsed_output={"action": "reject", "reason": "test"},
        cost_usd=0.01,
        created_at=utc_now_iso(),
    )

    store.put(checkpoint)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    assert store.get("k1") == checkpoint
    assert store.clear_for_ticker("ARWR") == 1
    assert store.get("k1") is None


def test_checkpoint_key_changes_when_prompt_hash_changes():
    key1 = checkpoint_key(
        run_date="2026-01-01",
        ticker="ARWR",
        stage="analyst",
        prompt_hash=stable_hash("prompt one"),
        model="claude-sonnet-4-6",
    )
    key2 = checkpoint_key(
        run_date="2026-01-01",
        ticker="ARWR",
        stage="analyst",
        prompt_hash=stable_hash("prompt two"),
        model="claude-sonnet-4-6",
    )

    assert key1 != key2


def test_checkpoint_reuse_skips_llm_calls_and_budget_for_completed_stages(tmp_path):
    store = AnalysisCheckpointStore(tmp_path / "checkpoints.jsonl")
    responses = [_PREFILTER_RESPONSE, _BUY_RESPONSE, _CHALLENGER_RESPONSE, _AUDITOR_RESPONSE]
    llm = SequenceLLMClient(responses)
    budget = DailyBudget(daily_limit_usd=999.0)
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        budget=budget,
        checkpoint_store=store,
        checkpoints_enabled=True,
        run_date="2026-01-01",
    )

    first = analyst.analyse([_event("ARWR")])
    first_spend = budget.spent_today()
    assert len(first) == 1
    assert len(llm.calls) == 4
    assert first_spend > 0

    second_llm = SequenceLLMClient([])
    second_budget = DailyBudget(daily_limit_usd=999.0)
    second_analyst = EquityAnalyst(
        second_llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        budget=second_budget,
        checkpoint_store=store,
        checkpoints_enabled=True,
        run_date="2026-01-01",
    )

    second = second_analyst.analyse([_event("ARWR")])

    assert len(second) == 1
    assert second_llm.calls == []
    assert second_budget.spent_today() == pytest.approx(0.0)


def test_prompt_change_invalidates_checkpoint(tmp_path):
    store = AnalysisCheckpointStore(tmp_path / "checkpoints.jsonl")
    first_llm = SequenceLLMClient([
        _PREFILTER_RESPONSE,
        _BUY_RESPONSE,
        _CHALLENGER_RESPONSE,
        _AUDITOR_RESPONSE,
    ])
    analyst = EquityAnalyst(
        first_llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        budget=DailyBudget(daily_limit_usd=999.0),
        checkpoint_store=store,
        checkpoints_enabled=True,
        run_date="2026-01-01",
    )
    assert analyst.analyse([_event("ARWR", evidence="Earnings in 5d")])

    second_llm = SequenceLLMClient([
        _PREFILTER_RESPONSE,
        _BUY_RESPONSE,
        _CHALLENGER_RESPONSE,
        _AUDITOR_RESPONSE,
    ])
    changed = EquityAnalyst(
        second_llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        budget=DailyBudget(daily_limit_usd=999.0),
        checkpoint_store=store,
        checkpoints_enabled=True,
        run_date="2026-01-01",
    )

    assert changed.analyse([_event("ARWR", evidence="Earnings in 6d")])
    assert second_llm.calls


def test_schema_invalid_checkpoint_is_ignored_and_rerun(tmp_path):
    store = AnalysisCheckpointStore(tmp_path / "checkpoints.jsonl")
    event = _event("ARWR")
    prompt = build_analyst_prompt(
        candidate=event,
        current_price=74.36,
        news=["headline 1", "headline 2"],
        filings=["8-K item 2.02 filed 3d ago"],
    )
    key = checkpoint_key(
        run_date="2026-01-01",
        ticker="ARWR",
        stage="analyst",
        prompt_hash=stable_hash(prompt),
        model="claude-sonnet-4-6",
    )
    store.put(
        AnalysisCheckpoint(
            key=key,
            ticker="ARWR",
            stage="analyst",
            model="claude-sonnet-4-6",
            prompt_hash=stable_hash(prompt),
            raw_output='{"action":"buy"}',
            parsed_output={"action": "buy"},
            cost_usd=0.0,
            created_at=utc_now_iso(),
        )
    )
    llm = SequenceLLMClient([
        _PREFILTER_RESPONSE,
        _BUY_RESPONSE,
        _CHALLENGER_RESPONSE,
        _AUDITOR_RESPONSE,
    ])
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        budget=DailyBudget(daily_limit_usd=999.0),
        checkpoint_store=store,
        checkpoints_enabled=True,
        run_date="2026-01-01",
    )

    assert analyst.analyse([event])
    assert len(llm.calls) == 4
