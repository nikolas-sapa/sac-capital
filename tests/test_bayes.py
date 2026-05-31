"""Tests for core.probability.bayes — written before implementation (TDD)."""
import pytest
from core.probability.bayes import posterior, is_shock


# ---------------------------------------------------------------------------
# posterior
# ---------------------------------------------------------------------------

def test_posterior_known_case_1():
    """prior=0.5, L_t=0.9, L_f=0.1 → 0.9"""
    result = posterior(0.5, 0.9, 0.1)
    assert abs(result - 0.9) < 1e-9


def test_posterior_known_case_2():
    """prior=0.2, L_t=0.8, L_f=0.4 → 0.16/0.48 = 1/3"""
    result = posterior(0.2, 0.8, 0.4)
    expected = (0.2 * 0.8) / (0.2 * 0.8 + 0.8 * 0.4)
    assert abs(result - expected) < 1e-9


def test_posterior_zero_denominator_returns_prior():
    """Both likelihoods 0 → denominator 0, return prior unchanged."""
    result = posterior(0.3, 0.0, 0.0)
    assert result == 0.3


def test_posterior_full_certainty():
    """prior=1.0, L_t=0.7, L_f=0.3 → always 1.0"""
    result = posterior(1.0, 0.7, 0.3)
    assert abs(result - 1.0) < 1e-9


def test_posterior_zero_prior():
    """prior=0.0 → posterior must be 0.0 regardless of likelihoods."""
    result = posterior(0.0, 0.9, 0.1)
    assert result == 0.0


# ---------------------------------------------------------------------------
# is_shock
# ---------------------------------------------------------------------------

def test_is_shock_above_threshold_within_window():
    """abs move 0.10 within 30s, pct=0.08 → True"""
    assert is_shock(0.5, 0.6, 30.0, pct=0.08, window=60) is True


def test_is_shock_below_threshold():
    """abs move 0.05 within 30s → False (below threshold)"""
    assert is_shock(0.5, 0.55, 30.0, pct=0.08, window=60) is False


def test_is_shock_outside_window():
    """abs move 0.10 but seconds=120 (> window 60) → False"""
    assert is_shock(0.5, 0.6, 120.0, pct=0.08, window=60) is False


def test_is_shock_exactly_at_threshold_not_shock():
    """Exactly 0.08 move → False (strictly greater than pct required)"""
    assert is_shock(0.5, 0.58, 30.0, pct=0.08, window=60) is False


def test_is_shock_negative_direction():
    """Downward move of 0.10 (prev=0.6, new=0.5) → True (absolute value)"""
    assert is_shock(0.6, 0.5, 30.0, pct=0.08, window=60) is True
