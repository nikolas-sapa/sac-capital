from datetime import datetime, timezone, timedelta

import pytest

from core.markets import Market, Outcome
from core.strategy import Signal
from strategies.llm_probability.budget import DailyBudget
from strategies.llm_probability.llm import LLMClient, ProbEstimate
from strategies.llm_probability.strategy import LLMProbabilityStrategy


def _market(yes_ask: float = 0.50) -> Market:
    return Market(
        condition_id="cond_x",
        question="Will X happen?",
        outcomes=[
            Outcome("yes", "Yes", yes_ask - 0.05, yes_ask),
            Outcome("no",  "No",  0.45, 0.52),
        ],
        end_date=datetime.now(tz=timezone.utc) + timedelta(days=5),
        closed=False,
    )


class _FixedClient:
    """Stub LLMClient that always returns a fixed estimate."""
    def __init__(self, probability: float, confidence: float = 0.8):
        self._est = ProbEstimate(probability=probability, confidence=confidence, reasoning="test")

    def estimate_probability(self, prompt: str) -> ProbEstimate:
        return self._est

    def prefilter(self, markets, max_candidates=10):
        return markets[:max_candidates]


def test_edge_above_threshold_emits_signal():
    strat = LLMProbabilityStrategy(client=_FixedClient(probability=0.70), min_edge=0.10, min_conf=0.60)
    signals = strat.scan([_market(yes_ask=0.50)])
    assert len(signals) == 1
    s = signals[0]
    assert isinstance(s, Signal)
    assert s.fair_prob == pytest.approx(0.70)
    assert s.price == pytest.approx(0.50)
    assert s.confidence == pytest.approx(0.80)
    assert s.token_id == "yes"


def test_edge_below_threshold_emits_nothing():
    strat = LLMProbabilityStrategy(client=_FixedClient(probability=0.52), min_edge=0.10, min_conf=0.60)
    signals = strat.scan([_market(yes_ask=0.50)])
    assert signals == []


def test_confidence_below_threshold_emits_nothing():
    strat = LLMProbabilityStrategy(client=_FixedClient(probability=0.75, confidence=0.40), min_edge=0.10, min_conf=0.60)
    signals = strat.scan([_market(yes_ask=0.50)])
    assert signals == []


def test_scan_multiple_markets_returns_all_above_threshold():
    strat = LLMProbabilityStrategy(client=_FixedClient(probability=0.75), min_edge=0.10)
    signals = strat.scan([_market(0.50), _market(0.50)])
    assert len(signals) == 2


def test_strategy_satisfies_protocol():
    from core.strategy import Strategy
    strat = LLMProbabilityStrategy(client=_FixedClient(0.70))
    assert isinstance(strat, Strategy)
