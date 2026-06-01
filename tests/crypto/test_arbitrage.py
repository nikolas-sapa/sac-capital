import pytest
from strategies.crypto_updown.arbitrage import find_arb, ArbSignal


def test_arb_found_when_sum_below_one_minus_fee():
    # ask_up=0.45, ask_down=0.45, fee=0.02 → total=0.92 < 1.0 → arb exists
    result = find_arb(ask_up=0.45, ask_down=0.45, fee_per_leg=0.02)
    assert result is not None
    assert isinstance(result, ArbSignal)


def test_no_arb_when_sum_at_or_above_one():
    # ask_up=0.50, ask_down=0.52, fee=0.01 → total=1.03 > 1.0
    assert find_arb(ask_up=0.50, ask_down=0.52, fee_per_leg=0.01) is None


def test_no_arb_when_fee_kills_edge():
    # ask_up=0.47, ask_down=0.47, fee=0.05 per leg → total cost=0.94+0.10=1.04
    assert find_arb(ask_up=0.47, ask_down=0.47, fee_per_leg=0.05) is None


def test_arb_profit_is_positive():
    result = find_arb(ask_up=0.45, ask_down=0.45, fee_per_leg=0.01)
    assert result is not None
    assert result.expected_profit_per_unit > 0.0


def test_arb_sizes_both_legs_equally():
    result = find_arb(ask_up=0.45, ask_down=0.45, fee_per_leg=0.01)
    assert result is not None
    assert result.size_up == result.size_down


def test_arb_profit_calculation():
    # buy Up at 0.44 + Down at 0.44, fee 0.01/leg
    # cost = 0.44 + 0.01 + 0.44 + 0.01 = 0.90
    # payout = 1.0 (exactly one resolves YES)
    # profit = 1.0 - 0.90 = 0.10 per unit
    result = find_arb(ask_up=0.44, ask_down=0.44, fee_per_leg=0.01)
    assert result is not None
    assert abs(result.expected_profit_per_unit - 0.10) < 0.001
