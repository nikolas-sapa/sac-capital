"""Tests for sizing A/B report."""
from __future__ import annotations

import pytest


def test_compare_sizing_basic_run() -> None:
    """Test core comparison function with 3-trade fixture."""
    from scripts.sizing_ab_report import compare_sizing

    # 3-trade fixture: some with shadow data, some without
    trades = [
        {
            "ticker": "AAPL",
            "shares": 10.0,
            "entry_price": 100.0,
            "exit_price": 105.0,
            "realized_pnl": 50.0,  # (105-100) * 10
            "sizing": {"kelly_shares": 10.0, "voltarget_shares": 8.0},
        },
        {
            "ticker": "GOOGL",
            "shares": 5.0,
            "entry_price": 200.0,
            "exit_price": 195.0,
            "realized_pnl": -25.0,  # (195-200) * 5
            "sizing": None,  # no shadow data
        },
        {
            "ticker": "MSFT",
            "shares": 15.0,
            "entry_price": 50.0,
            "exit_price": 52.0,
            "realized_pnl": 30.0,  # (52-50) * 15
            "sizing": {"kelly_shares": 15.0, "voltarget_shares": 12.0},
        },
    ]

    result = compare_sizing(trades)

    # Verify structure
    assert "kelly" in result
    assert "voltarget" in result
    assert "trades_with_shadow" in result

    # Kelly scheme: includes ALL trades (we always have actual shares)
    # AAPL: (105-100)*10 = 50, GOOGL: (195-200)*5 = -25, MSFT: (52-50)*15 = 30
    assert result["kelly"]["total_pnl"] == pytest.approx(50.0 - 25.0 + 30.0)  # all 3
    assert result["kelly"]["trade_count"] == 3
    assert result["kelly"]["mean_pnl"] == pytest.approx(55.0 / 3)  # 55 / 3

    # Vol-target scheme: hypothetical PnL using voltarget_shares (only for trades with shadow)
    # AAPL: (105 - 100) * 8 = 40 (instead of 50)
    # MSFT: (52 - 50) * 12 = 24 (instead of 30)
    assert result["voltarget"]["total_pnl"] == pytest.approx(40.0 + 24.0)
    assert result["voltarget"]["trade_count"] == 2  # only trades with shadow data
    assert result["voltarget"]["mean_pnl"] == pytest.approx(32.0)  # 64 / 2

    # Shadow trades count: 2 trades have sizing data
    assert result["trades_with_shadow"] == 2


def test_compare_sizing_empty() -> None:
    """When no trades have shadow data, Kelly still works."""
    from scripts.sizing_ab_report import compare_sizing

    trades = [
        {
            "ticker": "AAPL",
            "shares": 10.0,
            "entry_price": 100.0,
            "exit_price": 105.0,
            "realized_pnl": 50.0,
            "sizing": None,
        },
    ]

    result = compare_sizing(trades)

    # Kelly: always computed from actual shares
    assert result["kelly"]["total_pnl"] == 50.0
    assert result["kelly"]["trade_count"] == 1
    assert result["kelly"]["mean_pnl"] == pytest.approx(50.0)

    # Vol-target has no shadow data
    assert result["voltarget"]["total_pnl"] == 0.0
    assert result["voltarget"]["trade_count"] == 0

    # No trades with shadow sizing
    assert result["trades_with_shadow"] == 0


def test_compare_sizing_drawdown() -> None:
    """Verify max single-trade loss calculation."""
    from scripts.sizing_ab_report import compare_sizing

    trades = [
        {
            "ticker": "A",
            "shares": 10.0,
            "entry_price": 100.0,
            "exit_price": 95.0,
            "realized_pnl": -50.0,  # loss
            "sizing": {"kelly_shares": 10.0, "voltarget_shares": 8.0},
        },
        {
            "ticker": "B",
            "shares": 5.0,
            "entry_price": 100.0,
            "exit_price": 90.0,
            "realized_pnl": -50.0,  # same loss, fewer shares
            "sizing": {"kelly_shares": 5.0, "voltarget_shares": 4.0},
        },
    ]

    result = compare_sizing(trades)

    # Kelly: -50 is the max loss (tied with B)
    assert result["kelly"]["max_loss"] == pytest.approx(-50.0)

    # Vol-target: (90-100)*4 = -40, so max loss is -40
    assert result["voltarget"]["max_loss"] == pytest.approx(-40.0)
