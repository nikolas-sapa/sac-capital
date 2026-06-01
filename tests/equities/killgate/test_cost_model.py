import pytest
from equities.killgate.cost_model import entry_cost, exit_cost, net_pnl, round_trip_cost


def test_entry_cost_is_025_pct():
    cost = entry_cost(entry_price=100.0, shares=10.0)
    assert cost == pytest.approx(100.0 * 10.0 * 0.0025)


def test_exit_cost_no_gap():
    cost = exit_cost(exit_price=110.0, shares=10.0, is_gap_stop=False)
    assert cost == pytest.approx(110.0 * 10.0 * 0.0025)


def test_exit_cost_with_gap():
    # gap_pct=0.02 → actual exit = 110 * 0.98 = 107.8
    # commission = 107.8 * 10 * 0.0025
    # slippage = (110 - 107.8) * 10 = 22.0
    cost = exit_cost(exit_price=110.0, shares=10.0, is_gap_stop=True, gap_pct=0.02)
    expected = 107.8 * 10.0 * 0.0025 + 22.0
    assert cost == pytest.approx(expected)


def test_net_pnl_winning_trade():
    # entry=100, exit=110, shares=10
    # gross = 100, round trip cost = (100*10 + 110*10) * 0.0025 = 5.25
    pnl = net_pnl(100.0, 110.0, 10.0, is_gap_stop=False)
    gross = (110.0 - 100.0) * 10.0
    cost = round_trip_cost(100.0, 110.0, 10.0)
    assert pnl == pytest.approx(gross - cost)


def test_net_pnl_losing_trade():
    pnl = net_pnl(100.0, 90.0, 10.0, is_gap_stop=False)
    assert pnl < 0


def test_gap_stop_reduces_net_pnl():
    no_gap = net_pnl(100.0, 95.0, 10.0, is_gap_stop=False)
    with_gap = net_pnl(100.0, 95.0, 10.0, is_gap_stop=True)
    assert with_gap < no_gap
