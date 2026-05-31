"""Tests for core/execution/paper.py — TDD written before implementation.

Step 1: All tests in this file must FAIL before PaperExecutor exists.
Step 3: All tests must PASS after implementation.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _market(condition_id: str = "cond-paper") -> Market:
    return Market(
        condition_id=condition_id,
        question="Will X happen?",
        outcomes=[
            Outcome(token_id="tok-yes", label="Yes", best_bid=0.55, best_ask=0.56),
            Outcome(token_id="tok-no", label="No", best_bid=0.43, best_ask=0.44),
        ],
        end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
        closed=False,
    )


def _signal(price: float = 0.56, market: Market | None = None) -> Signal:
    return Signal(
        market=market or _market(),
        token_id="tok-yes",
        fair_prob=0.65,
        price=price,
        confidence=0.8,
        reason="test reason",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_place_returns_fill_with_paper_mode(tmp_path):
    """place() returns a Fill with mode == 'paper'."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    executor = PaperExecutor(ledger)
    signal = _signal()

    fill = executor.place(signal, stake=10.0)

    assert isinstance(fill, Fill)
    assert fill.mode == "paper"


def test_place_no_slippage_no_fee_exact_shares(tmp_path):
    """With slippage=0.0, fee_rate=0.0: shares == stake / price, avg_price == signal.price."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)
    price = 0.56
    stake = 10.0
    signal = _signal(price=price)

    fill = executor.place(signal, stake=stake)

    assert fill.avg_price == pytest.approx(price, abs=1e-9)
    assert fill.shares == pytest.approx(stake / price, abs=1e-9)


def test_place_with_slippage(tmp_path):
    """With slippage=0.01: avg_price == signal.price * 1.01, shares == stake / avg_price."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    executor = PaperExecutor(ledger, slippage=0.01, fee_rate=0.0)
    price = 0.56
    stake = 10.0
    signal = _signal(price=price)

    fill = executor.place(signal, stake=stake)

    expected_exec_price = price * 1.01
    assert fill.avg_price == pytest.approx(expected_exec_price, abs=1e-9)
    assert fill.shares == pytest.approx(stake / expected_exec_price, abs=1e-9)


def test_place_with_fee_rate(tmp_path):
    """With fee_rate=0.02: shares == (stake / exec_price) * 0.98."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.02)
    price = 0.56
    stake = 10.0
    signal = _signal(price=price)

    fill = executor.place(signal, stake=stake)

    exec_price = price  # slippage=0.0
    expected_shares = (stake / exec_price) * 0.98
    assert fill.shares == pytest.approx(expected_shares, abs=1e-9)


def test_exec_price_capped_below_one(tmp_path):
    """exec_price is capped at 0.999 — never >= 1.0 (prices are probabilities)."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    # signal.price=0.999, slippage=0.01 → uncapped would be 0.999*1.01 = 1.00899
    executor = PaperExecutor(ledger, slippage=0.01, fee_rate=0.0)
    signal = _signal(price=0.999)

    fill = executor.place(signal, stake=10.0)

    assert fill.avg_price == pytest.approx(0.999, abs=1e-9)
    assert fill.avg_price < 1.0


def test_timestamp_is_utc_aware(tmp_path):
    """Fill timestamp must be timezone-aware UTC."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    executor = PaperExecutor(ledger)
    signal = _signal()

    fill = executor.place(signal, stake=10.0)

    assert fill.timestamp.tzinfo is not None
    assert fill.timestamp.utcoffset().total_seconds() == 0


def test_place_records_in_ledger(tmp_path):
    """After place(), the injected Ledger's open_positions() returns 1 row with matching stake/shares."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)
    price = 0.56
    stake = 10.0
    signal = _signal(price=price)

    fill = executor.place(signal, stake=stake)

    positions = ledger.open_positions()
    assert len(positions) == 1
    pos = positions[0]
    assert pos["stake"] == pytest.approx(stake, abs=1e-9)
    assert pos["shares"] == pytest.approx(fill.shares, abs=1e-9)
    assert pos["avg_price"] == pytest.approx(fill.avg_price, abs=1e-9)


def test_place_forwards_strategy_to_ledger(tmp_path):
    """place(signal, stake, strategy=...) stores strategy in the ledger."""
    from core.execution.paper import PaperExecutor

    ledger = Ledger(tmp_path / "ledger.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)
    signal = _signal()

    executor.place(signal, stake=10.0, strategy="weather")

    positions = ledger.open_positions()
    assert len(positions) == 1
    assert positions[0]["strategy"] == "weather"
