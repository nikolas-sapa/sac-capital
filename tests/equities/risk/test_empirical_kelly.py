import pytest

from equities.risk.sizing import empirical_kelly_risk_pct


def test_kelly_math():
    # p=0.6, b=2: f* = (2*0.6 - 0.4)/2 = 0.4; fraction 0.5 -> 0.20
    assert empirical_kelly_risk_pct(0.6, 2.0, kelly_fraction=0.5) == pytest.approx(0.20)


def test_negative_edge_returns_none():
    # p=0.3, b=1: bp - q = 0.3 - 0.7 < 0 -> no Kelly bet
    assert empirical_kelly_risk_pct(0.3, 1.0, kelly_fraction=0.5) is None


def test_fraction_hard_capped_at_half():
    # env says 0.85 -> effective fraction 0.5 (over-Kelly is ruin math, not aggression)
    full = empirical_kelly_risk_pct(0.6, 2.0, kelly_fraction=1.0, hard_cap=0.5)
    env = empirical_kelly_risk_pct(0.6, 2.0, kelly_fraction=0.85, hard_cap=0.5)
    assert env == full == pytest.approx(0.20)
