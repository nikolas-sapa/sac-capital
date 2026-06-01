"""Tests for RiskKernel fuses."""
from core.assets.instrument import CapTier, Instrument
from equities.risk.kernel import RiskKernel, SizedRecommendation
from equities.strategy import Recommendation, Sleeve


def _rec(
    ticker: str = "ARWR",
    entry: float = 74.0,
    stop: float = 68.0,
    tp: float = 88.0,
) -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        size_pct=0.02,
        confidence=0.72,
        catalyst="test",
        thesis="test thesis",
        horizon="2 weeks",
    )


def _open_pos(ticker: str = "X", shares: float = 10.0, price: float = 50.0) -> dict:
    return {"ticker": ticker, "sleeve": "swing", "shares": shares, "entry_price": price, "status": "open"}


def test_approves_valid_recommendation():
    kernel = RiskKernel(capital=1000.0)
    result = kernel.approve(_rec(), open_positions=[])
    assert result.approved is True
    assert result.shares > 0


def test_rejects_when_max_positions_reached():
    kernel = RiskKernel(capital=1000.0, max_positions=2)
    open_pos = [_open_pos("A"), _open_pos("B")]
    result = kernel.approve(_rec(), open_positions=open_pos)
    assert result.approved is False
    assert "max_positions" in result.rejection_reason


def test_rejects_when_daily_loss_exceeded():
    kernel = RiskKernel(capital=1000.0, daily_loss_limit_pct=0.05)
    result = kernel.approve(_rec(), open_positions=[], today_realized_loss=-100.0)
    assert result.approved is False
    assert "daily_loss" in result.rejection_reason


def test_rejects_on_drawdown():
    kernel = RiskKernel(capital=1000.0, drawdown_limit_pct=0.15)
    # current equity 800 → drawdown = 20% > 15%
    result = kernel.approve(_rec(), open_positions=[], current_equity=800.0)
    assert result.approved is False
    assert "drawdown" in result.rejection_reason


def test_circuit_breaker_stays_halted():
    kernel = RiskKernel(capital=1000.0, drawdown_limit_pct=0.10)
    kernel.approve(_rec(), open_positions=[], current_equity=880.0)  # trips breaker
    result = kernel.approve(_rec(), open_positions=[])
    assert result.approved is False
    assert "circuit_breaker" in result.rejection_reason


def test_shares_positive_on_valid_input():
    kernel = RiskKernel(capital=10_000.0, risk_pct=0.01)
    result = kernel.approve(_rec(entry=100.0, stop=90.0), open_positions=[])
    assert result.approved is True
    assert result.shares > 0


def test_rejects_missing_stop_loss():
    kernel = RiskKernel(capital=1000.0)
    rec = _rec()
    # Manually create a recommendation with no stop
    import dataclasses
    no_stop = dataclasses.replace(rec, stop_loss=None)
    result = kernel.approve(no_stop, open_positions=[])
    assert result.approved is False
