import pytest
from strategies.llm_probability.calibration import brier_score, calibration_buckets


def test_perfect_predictor_brier_zero():
    # Always predicts 1.0 for outcomes that resolve YES
    pairs = [(1.0, True), (0.0, False)]
    assert brier_score(pairs) == pytest.approx(0.0)


def test_worst_predictor_brier_one():
    # Always exactly wrong
    pairs = [(1.0, False), (0.0, True)]
    assert brier_score(pairs) == pytest.approx(1.0)


def test_random_predictor_brier_near_quarter():
    # p=0.5 always → Brier = 0.25 regardless of outcome
    pairs = [(0.5, True), (0.5, False), (0.5, True), (0.5, False)]
    assert brier_score(pairs) == pytest.approx(0.25)


def test_brier_raises_on_empty():
    with pytest.raises(ValueError):
        brier_score([])


def test_calibration_buckets_returns_buckets():
    pairs = [
        (0.1, False), (0.2, False), (0.5, True), (0.5, False),
        (0.7, True), (0.8, True), (0.9, True),
    ]
    buckets = calibration_buckets(pairs, n_buckets=5)
    assert isinstance(buckets, list)
    assert all("predicted" in b and "actual" in b and "count" in b for b in buckets)


def test_calibration_buckets_actual_in_range():
    pairs = [(0.3, False), (0.7, True), (0.9, True), (0.1, False)]
    buckets = calibration_buckets(pairs, n_buckets=5)
    for b in buckets:
        assert 0.0 <= b["actual"] <= 1.0


def test_calibration_skips_empty_buckets():
    pairs = [(0.9, True), (0.95, True)]
    buckets = calibration_buckets(pairs, n_buckets=10)
    assert all(b["count"] > 0 for b in buckets)
