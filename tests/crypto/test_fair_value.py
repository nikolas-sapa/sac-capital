import pytest
from strategies.weather.consensus import ConsensusResult  # noqa: F401 (verify import works)
from strategies.crypto_updown.fair_value import fair_up_prob


def test_atm_with_time_left_is_near_half():
    p = fair_up_prob(spot_now=67000.0, strike=67000.0, seconds_left=3600, vol=0.01)
    assert abs(p - 0.5) < 0.05


def test_far_above_strike_near_expiry_approaches_one():
    p = fair_up_prob(spot_now=70350.0, strike=67000.0, seconds_left=60, vol=0.01)
    assert p > 0.90


def test_far_below_strike_near_expiry_approaches_zero():
    p = fair_up_prob(spot_now=63650.0, strike=67000.0, seconds_left=60, vol=0.01)
    assert p < 0.10


def test_short_expiry_is_more_decisive_than_long():
    # spot above strike — less time → probability further from 0.5
    p_short = fair_up_prob(67500.0, 67000.0, seconds_left=300,   vol=0.01)
    p_long  = fair_up_prob(67500.0, 67000.0, seconds_left=86400, vol=0.01)
    assert p_short > p_long


def test_output_bounded():
    for spot, strike, secs in [(50000, 70000, 10), (90000, 60000, 10), (67000, 67000, 3600)]:
        p = fair_up_prob(spot, strike, secs, vol=0.015)
        assert 0.0 < p < 1.0


def test_high_vol_pulls_toward_half():
    p_low  = fair_up_prob(69000.0, 67000.0, seconds_left=600, vol=0.001)
    p_high = fair_up_prob(69000.0, 67000.0, seconds_left=600, vol=0.50)
    assert abs(p_high - 0.5) < abs(p_low - 0.5)
