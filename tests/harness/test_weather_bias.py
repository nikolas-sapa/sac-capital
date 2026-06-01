import pytest
from harness.learn.weather_bias import learn_bias


def test_returns_zero_below_min_n():
    samples = [(20.0, 21.0)] * 10  # only 10 < 20
    assert learn_bias(samples, min_n=20) == 0.0


def test_detects_warm_bias():
    # Actual is always 2°C warmer than forecast
    samples = [(20.0, 22.0)] * 25
    bias = learn_bias(samples, min_n=20)
    assert bias == pytest.approx(0.5)  # capped at max_step=0.5


def test_detects_cold_bias():
    # Actual is always 2°C colder than forecast
    samples = [(20.0, 18.0)] * 25
    bias = learn_bias(samples, min_n=20)
    assert bias == pytest.approx(-0.5)  # capped at -max_step


def test_small_bias_not_capped():
    # Actual is 0.3°C warmer → well within max_step=0.5
    samples = [(20.0, 20.3)] * 25
    bias = learn_bias(samples, min_n=20)
    assert abs(bias - 0.3) < 0.01


def test_exactly_at_min_n():
    samples = [(15.0, 16.0)] * 20
    bias = learn_bias(samples, min_n=20)
    assert bias == pytest.approx(0.5)  # capped


def test_custom_max_step():
    samples = [(20.0, 21.0)] * 25  # true bias = 1.0
    bias = learn_bias(samples, min_n=20, max_step=0.3)
    assert bias == pytest.approx(0.3)
