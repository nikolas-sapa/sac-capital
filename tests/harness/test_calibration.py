import pytest
from harness.learn.calibration import fit_calibrator, Calibrator


def test_returns_none_below_min_n():
    samples = [(0.6, 1), (0.4, 0)] * 10  # only 20 < 50
    assert fit_calibrator(samples, min_n=50) is None


def test_returns_calibrator_at_min_n():
    samples = [(0.6, 1), (0.4, 0)] * 25  # exactly 50
    cal = fit_calibrator(samples, min_n=50)
    assert cal is not None
    assert isinstance(cal, Calibrator)


def test_calibrated_output_in_range():
    samples = [(0.6, 1), (0.4, 0)] * 30  # 60 samples
    cal = fit_calibrator(samples, min_n=50)
    assert cal is not None
    result = cal.apply(0.55)
    assert 0.0 <= result <= 1.0


def test_overconfident_forecaster_pulled_toward_true_frequency():
    # Always predicts 0.9 but only wins 50% → calibrated output should be near 0.5
    samples = [(0.9, 1)] * 30 + [(0.9, 0)] * 30
    cal = fit_calibrator(samples, min_n=50)
    assert cal is not None
    corrected = cal.apply(0.9)
    assert corrected < 0.9  # pulled toward the true 0.5 frequency


def test_underconfident_forecaster_pulled_up():
    # Always predicts 0.1 but wins 80% → calibrated output should be above 0.1
    samples = [(0.1, 1)] * 40 + [(0.1, 0)] * 10
    cal = fit_calibrator(samples, min_n=50)
    assert cal is not None
    corrected = cal.apply(0.1)
    assert corrected > 0.1
