"""Tests for signal fusion formula (_compute_build_action)."""
from __future__ import annotations

from equities.analysis.analyst import _compute_build_action


def test_high_confidence_gives_aggressive_build():
    action, size_pct = _compute_build_action(analyst_confidence=0.85, consistency_penalty=0.05)
    assert action == "AGGRESSIVE_BUILD"
    assert size_pct == 0.04


def test_medium_confidence_gives_gradual_build():
    action, size_pct = _compute_build_action(analyst_confidence=0.70, consistency_penalty=0.05)
    assert action == "GRADUAL_BUILD"
    assert size_pct == 0.02


def test_low_medium_confidence_gives_nibble():
    action, size_pct = _compute_build_action(analyst_confidence=0.55, consistency_penalty=0.05)
    assert action == "NIBBLE"
    assert size_pct == 0.01


def test_low_confidence_gives_wait():
    action, size_pct = _compute_build_action(analyst_confidence=0.50, consistency_penalty=0.10)
    assert action == "WAIT"
    assert size_pct == 0.0


def test_composite_clamped_at_zero():
    action, size_pct = _compute_build_action(analyst_confidence=0.10, consistency_penalty=0.20)
    assert action == "WAIT"
    assert size_pct == 0.0
