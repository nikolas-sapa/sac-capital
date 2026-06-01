import pytest
from equities.improve.tournament import TournamentResult, run_tournament
from equities.improve.variants import ParameterVariant


def _score(trades, params):
    """Mock: count trades where value > threshold."""
    return sum(1 for t in trades if t.get("value", 0) > params.get("threshold", 0.5))


def _variant(name: str, threshold: float) -> ParameterVariant:
    return ParameterVariant(name=name, params={"threshold": threshold})


def test_returns_none_on_insufficient_trades():
    variants = [_variant("base", 0.5)]
    result = run_tournament(variants, [{"value": 0.6}] * 3, _score)
    assert result is None


def test_picks_winner_with_best_oos_score():
    trades = [{"value": 0.3}] * 6 + [{"value": 0.7}] * 4
    # OOS window: last 40% = 4 trades with value=0.7
    # threshold=0.5 scores 4 (0.7 > 0.5), threshold=0.8 scores 0
    variants = [_variant("low", 0.5), _variant("high", 0.8)]
    result = run_tournament(variants, trades, _score)
    assert result is not None
    assert result.winner.name == "low"


def test_winner_evaluated_on_oos_only():
    # in-sample: 6 trades value=0.9 (all above any threshold)
    # OOS: 4 trades value=0.1 (all below 0.5, none below 0.05)
    trades = [{"value": 0.9}] * 6 + [{"value": 0.1}] * 4
    variants = [_variant("strict", 0.5), _variant("lenient", 0.05)]
    result = run_tournament(variants, trades, _score)
    assert result is not None
    # lenient (0.05) scores 4 on OOS; strict (0.5) scores 0
    assert result.winner.name == "lenient"


def test_result_includes_n_validated():
    trades = [{"value": 0.6}] * 10
    variants = [_variant("v1", 0.5)]
    result = run_tournament(variants, trades, _score)
    assert result is not None
    assert result.n_validated == 4  # 40% of 10
