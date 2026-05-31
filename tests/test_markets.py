from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from core.markets import Market, Outcome


def make_outcome(token_id: str = "tok1") -> Outcome:
    return Outcome(
        token_id=token_id,
        label="Yes",
        best_bid=0.45,
        best_ask=0.47,
    )


def make_market(outcomes: list[Outcome] | None = None) -> Market:
    if outcomes is None:
        outcomes = [make_outcome("tok1"), make_outcome("tok2")]
    return Market(
        condition_id="cond123",
        question="Will X happen?",
        outcomes=outcomes,
        end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        closed=False,
    )


class TestOutcome:
    def test_construct(self):
        o = make_outcome()
        assert o.token_id == "tok1"
        assert o.label == "Yes"
        assert o.best_bid == 0.45
        assert o.best_ask == 0.47

    def test_frozen(self):
        o = make_outcome()
        with pytest.raises(FrozenInstanceError):
            o.label = "No"  # type: ignore[misc]


class TestMarket:
    def test_construct(self):
        m = make_market()
        assert m.condition_id == "cond123"
        assert m.question == "Will X happen?"
        assert len(m.outcomes) == 2
        assert m.closed is False

    def test_frozen(self):
        m = make_market()
        with pytest.raises(FrozenInstanceError):
            m.condition_id = "other"  # type: ignore[misc]

    def test_outcome_by_token_found(self):
        o1 = make_outcome("tok1")
        o2 = make_outcome("tok2")
        m = make_market([o1, o2])
        assert m.outcome_by_token("tok1") is o1
        assert m.outcome_by_token("tok2") is o2

    def test_outcome_by_token_missing(self):
        m = make_market()
        with pytest.raises(KeyError, match="unknown_tok"):
            m.outcome_by_token("unknown_tok")
