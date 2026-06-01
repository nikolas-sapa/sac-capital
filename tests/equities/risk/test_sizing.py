import pytest
from equities.risk.sizing import size_shares


def test_basic_sizing():
    # capital=1000, risk=2%, entry=50, stop=45 → stop_dist_gap = 50 - 45*(1-0.02) = 50-44.1 = 5.9
    # shares = 1000*0.02 / 5.9 ≈ 3.39
    shares = size_shares(capital=1000.0, risk_pct=0.02, entry=50.0, stop_loss=45.0, gap_pct=0.02)
    assert shares == pytest.approx(1000.0 * 0.02 / (50.0 - 45.0 * 0.98), rel=1e-4)


def test_zero_shares_when_entry_below_stop():
    assert size_shares(1000.0, 0.02, 40.0, 50.0) == 0.0


def test_zero_shares_when_entry_equals_stop():
    assert size_shares(1000.0, 0.02, 50.0, 50.0) == 0.0


def test_larger_stop_distance_fewer_shares():
    tight = size_shares(1000.0, 0.02, 100.0, 95.0)
    wide = size_shares(1000.0, 0.02, 100.0, 80.0)
    assert tight > wide


def test_higher_risk_pct_more_shares():
    low = size_shares(1000.0, 0.01, 100.0, 95.0)
    high = size_shares(1000.0, 0.02, 100.0, 95.0)
    assert high > low


def test_gap_pct_zero_no_penalty():
    shares_no_gap = size_shares(1000.0, 0.02, 50.0, 45.0, gap_pct=0.0)
    assert shares_no_gap == pytest.approx(1000.0 * 0.02 / 5.0, rel=1e-6)


def test_invalid_inputs_return_zero():
    assert size_shares(0.0, 0.02, 50.0, 45.0) == 0.0   # zero capital
    assert size_shares(1000.0, 0.0, 50.0, 45.0) == 0.0  # zero risk
    assert size_shares(1000.0, 1.5, 50.0, 45.0) == 0.0  # risk > 100%
