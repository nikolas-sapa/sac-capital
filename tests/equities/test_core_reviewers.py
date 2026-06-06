from __future__ import annotations

import json

from core.assets.instrument import CapTier, Instrument
from equities.analysis.analyst import LLMResponse
from equities.analysis.core_analyst import CoreDCAAnalyst
from equities.analysis.core_reviewers import (
    format_core_reviews,
    has_hard_reject,
    run_core_reviewers,
)
from equities.data.fundamentals import FundamentalsSnapshot
from equities.screen.quality_screen import QualityCandidate


def _snapshot(**overrides) -> FundamentalsSnapshot:
    data = {
        "ticker": "MSFT",
        "market_cap_m": 2_000_000.0,
        "trailing_pe": 32.0,
        "forward_pe": 28.0,
        "gross_margins": 0.68,
        "revenue_growth": 0.12,
        "sector": "Technology",
        "analyst_count": 30,
        "eps_trend": [2.1, 2.2, 2.4, 2.6],
        "peg_ratio": 1.8,
        "operating_margins": 0.42,
        "debt_to_equity": 60.0,
        "free_cash_flow_m": 50_000.0,
    }
    data.update(overrides)
    return FundamentalsSnapshot(**data)


def _candidate() -> QualityCandidate:
    return QualityCandidate(
        instrument=Instrument("MSFT", "Microsoft", "NASDAQ", CapTier.LARGE),
        score=0.8,
        evidence="gross_margins=68% | trailing_pe=32.0 | rev_growth=+12%",
    )


class FakePrice:
    def latest_close(self, ticker: str) -> float | None:
        return 100.0


class FakeNews:
    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        return ["steady product demand"]


class FakeFundamentals:
    def __init__(self, snap: FundamentalsSnapshot) -> None:
        self._snap = snap

    def fetch(self, ticker: str) -> FundamentalsSnapshot:
        return self._snap


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content=json.dumps({
                "action": "dca",
                "dca_pct": 0.01,
                "thesis": "Quality compounder remains suitable for core accumulation.",
            }),
            input_tokens=100,
            output_tokens=50,
        )


def test_core_reviewers_approve_high_quality_candidate():
    reviews = run_core_reviewers(_snapshot())

    assert not has_hard_reject(reviews)
    assert all(review.verdict == "approve" for review in reviews)
    assert "balance_sheet: approve" in format_core_reviews(reviews)


def test_core_reviewers_hard_reject_poor_balance_sheet():
    reviews = run_core_reviewers(
        _snapshot(debt_to_equity=320.0, free_cash_flow_m=-500.0)
    )

    assert has_hard_reject(reviews)
    assert any(review.reviewer == "balance_sheet" and review.verdict == "reject" for review in reviews)


def test_core_reviewers_surface_disagreement_without_hard_reject():
    reviews = run_core_reviewers(_snapshot(forward_pe=55.0, peg_ratio=3.5))

    assert not has_hard_reject(reviews)
    assert any(review.verdict == "wait" for review in reviews)
    assert "valuation: wait" in format_core_reviews(reviews)


def test_core_dca_skips_llm_on_hard_reject():
    llm = FakeLLM()
    analyst = CoreDCAAnalyst(
        llm=llm,
        prices=FakePrice(),
        news=FakeNews(),
        fundamentals=FakeFundamentals(
            _snapshot(debt_to_equity=320.0, free_cash_flow_m=-500.0)
        ),
    )

    assert analyst.analyse([_candidate()]) == []
    assert llm.calls == 0


def test_core_dca_includes_reviewer_packet_for_high_quality_candidate():
    llm = FakeLLM()
    analyst = CoreDCAAnalyst(
        llm=llm,
        prices=FakePrice(),
        news=FakeNews(),
        fundamentals=FakeFundamentals(_snapshot()),
    )

    results = analyst.analyse([_candidate()])

    assert len(results) == 1
    assert llm.calls == 1
    assert results[0].memo is not None
    assert "core_reviewer_checks" in results[0].memo
