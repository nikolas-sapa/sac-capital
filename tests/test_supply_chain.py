"""Tests for supply chain graph and BottleneckScorer."""
from __future__ import annotations

from equities.research.supply_chain import (
    SUPPLY_CHAIN,
    BottleneckScorer,
    get_leaves_for_trunk,
    get_trunks_for_leaf,
)


def test_nvda_has_expected_leaves():
    leaves = get_leaves_for_trunk("NVDA")
    assert "MU" in leaves
    assert "COHR" in leaves
    assert "AMKR" in leaves


def test_unknown_trunk_returns_empty():
    assert get_leaves_for_trunk("FAKECO") == []


def test_leaf_trunks_lookup():
    trunks = get_trunks_for_leaf("MU")
    assert "NVDA" in trunks


def test_bottleneck_score_range():
    scorer = BottleneckScorer()
    score = scorer.score("MU", trunk="NVDA")
    assert 0.0 <= score <= 1.0


def test_asml_monopoly_scores_near_one():
    scorer = BottleneckScorer()
    assert scorer.score("ASML", trunk="TSM") > 0.8


def test_top_strategy_universe_names_present():
    assert {"AMAT", "LRCX", "ENTG"}.issubset(set(SUPPLY_CHAIN["TSM"]))
    assert {"COHR", "MU"}.issubset(set(SUPPLY_CHAIN["NVDA"]))
    assert "AMAT" in SUPPLY_CHAIN["AMD"]
