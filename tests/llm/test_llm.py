import pytest

from strategies.llm_probability.llm import LLMClient, ProbEstimate
from strategies.llm_probability.budget import DailyBudget


class _MockClient:
    """Fake LLM that returns a fixed JSON string."""
    def __init__(self, response: str):
        self._response = response
        self.calls: list[str] = []

    def complete(self, prompt: str, *, model: str) -> str:
        self.calls.append(prompt)
        return self._response

    def complete_batch(self, prompts: list[str], *, model: str) -> list[str]:
        return [self._response for _ in prompts]


_GOOD_JSON = '{"probability": 0.72, "confidence": 0.65, "reasoning": "Strong evidence."}'
_BAD_JSON  = "not json at all"
_OOB_JSON  = '{"probability": 1.5, "confidence": 0.5, "reasoning": "oob"}'


def _client(resp: str = _GOOD_JSON, limit: float = 5.0) -> LLMClient:
    budget = DailyBudget(limit_usd=limit)
    return LLMClient(backend=_MockClient(resp), budget=budget)


def test_estimate_parses_valid_response():
    est = _client().estimate_probability("some prompt")
    assert isinstance(est, ProbEstimate)
    assert est.probability == pytest.approx(0.72)
    assert est.confidence == pytest.approx(0.65)
    assert "Strong" in est.reasoning


def test_estimate_retries_on_bad_json():
    # Second call succeeds — the mock always returns the same thing so we
    # simulate retry by giving a client whose second response is valid.
    class _RetryMock:
        def __init__(self):
            self._calls = 0
        def complete(self, prompt, *, model):
            self._calls += 1
            return _GOOD_JSON if self._calls > 1 else _BAD_JSON
        def complete_batch(self, prompts, *, model):
            return [self.complete(p, model=model) for p in prompts]

    budget = DailyBudget(limit_usd=5.0)
    c = LLMClient(backend=_RetryMock(), budget=budget)
    est = c.estimate_probability("prompt")
    assert est.probability == pytest.approx(0.72)


def test_estimate_raises_after_two_bad_responses():
    budget = DailyBudget(limit_usd=5.0)
    c = LLMClient(backend=_MockClient(_BAD_JSON), budget=budget)
    with pytest.raises(ValueError, match="parse"):
        c.estimate_probability("prompt")


def test_estimate_rejects_out_of_range_probability():
    budget = DailyBudget(limit_usd=5.0)
    c = LLMClient(backend=_MockClient(_OOB_JSON), budget=budget)
    with pytest.raises(ValueError, match="range"):
        c.estimate_probability("prompt")


def test_budget_guard_blocks_call():
    c = _client(limit=0.0)  # zero budget
    with pytest.raises(RuntimeError, match="budget"):
        c.estimate_probability("prompt")


def test_prefilter_returns_subset():
    from datetime import datetime, timezone, timedelta
    from core.markets import Market, Outcome

    def _m(q: str) -> Market:
        return Market(
            condition_id=q,
            question=q,
            outcomes=[Outcome("y", "Yes", 0.4, 0.5), Outcome("n", "No", 0.5, 0.55)],
            end_date=datetime.now(tz=timezone.utc) + timedelta(days=5),
            closed=False,
        )

    markets = [_m(f"q{i}") for i in range(6)]
    c = _client()
    # prefilter should return a list (possibly trimmed) without hitting Sonnet
    result = c.prefilter(markets, max_candidates=3)
    assert len(result) <= 3
    assert all(hasattr(m, "question") for m in result)
