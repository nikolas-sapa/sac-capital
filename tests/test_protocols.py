"""TDD tests for Strategy/Executor protocols and Signal/Fill types."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from core.markets import Market, Outcome
from core.strategy import Signal, Strategy
from core.execution.base import Fill, Executor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_market() -> Market:
    outcome = Outcome(token_id="tok1", label="Yes", best_bid=0.45, best_ask=0.50)
    return Market(
        condition_id="cond1",
        question="Will X happen?",
        outcomes=[outcome],
        end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
        closed=False,
    )


def _make_signal(market: Market) -> Signal:
    return Signal(
        market=market,
        token_id="tok1",
        fair_prob=0.65,
        price=0.50,
        confidence=0.8,
        reason="test reason",
    )


# ---------------------------------------------------------------------------
# Dummy implementations (defined in test — not in core)
# ---------------------------------------------------------------------------

class DummyStrategy:
    name = "dummy"

    def scan(self, markets: list[Market]) -> list[Signal]:
        return []


class DummyExecutor:
    def place(self, signal: Signal, stake: float) -> Fill:
        return Fill(
            signal=signal,
            stake=stake,
            shares=stake / signal.price,
            avg_price=signal.price,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            mode="paper",
        )


class IncompleteExecutor:
    """Missing place() — should NOT be an instance of Executor."""
    pass


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------

class TestSignal:
    def test_construct(self):
        market = _make_market()
        sig = _make_signal(market)
        assert sig.market is market
        assert sig.token_id == "tok1"
        assert sig.fair_prob == 0.65
        assert sig.price == 0.50
        assert sig.confidence == 0.8
        assert sig.reason == "test reason"

    def test_frozen(self):
        market = _make_market()
        sig = _make_signal(market)
        with pytest.raises(Exception):  # FrozenInstanceError
            sig.fair_prob = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Fill tests
# ---------------------------------------------------------------------------

class TestFill:
    def test_construct(self):
        market = _make_market()
        sig = _make_signal(market)
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        fill = Fill(
            signal=sig,
            stake=10.0,
            shares=20.0,
            avg_price=0.50,
            timestamp=ts,
            mode="paper",
        )
        assert fill.signal is sig
        assert fill.stake == 10.0
        assert fill.shares == 20.0
        assert fill.avg_price == 0.50
        assert fill.timestamp == ts
        assert fill.mode == "paper"

    def test_frozen(self):
        market = _make_market()
        sig = _make_signal(market)
        fill = Fill(
            signal=sig,
            stake=5.0,
            shares=10.0,
            avg_price=0.50,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            mode="paper",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            fill.stake = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Protocol isinstance checks
# ---------------------------------------------------------------------------

class TestStrategyProtocol:
    def test_dummy_is_strategy(self):
        assert isinstance(DummyStrategy(), Strategy)

    def test_dummy_instance_scan(self):
        market = _make_market()
        result = DummyStrategy().scan([market])
        assert result == []


class TestExecutorProtocol:
    def test_dummy_is_executor(self):
        assert isinstance(DummyExecutor(), Executor)

    def test_incomplete_is_not_executor(self):
        assert not isinstance(IncompleteExecutor(), Executor)

    def test_dummy_place(self):
        market = _make_market()
        sig = _make_signal(market)
        fill = DummyExecutor().place(sig, 10.0)
        assert fill.stake == 10.0
        assert fill.mode == "paper"
