import pytest
from harness.learn.retune import retune


def _score(trades, param):
    """Mock validate_fn: reward trades where 'value' > param (the threshold)."""
    return sum(1 for t in trades if t.get("value", 0) > param)


def test_returns_current_below_min_trades():
    result = retune(
        param_grid=[0.05, 0.08, 0.10],
        resolved_trades=[{"value": 0.1}] * 3,  # < 4
        validate_fn=_score,
        max_step=0.05,
        current_value=0.08,
    )
    assert result == 0.08


def test_stays_within_max_step():
    # current=0.08, max_step=0.03 → candidates within [0.05, 0.11]
    result = retune(
        param_grid=[0.05, 0.08, 0.10, 0.15],
        resolved_trades=[{"value": 0.12}] * 10,
        validate_fn=_score,
        max_step=0.03,
        current_value=0.08,
    )
    assert abs(result - 0.08) <= 0.03 + 1e-9


def test_picks_best_out_of_sample_value():
    # validate_fn rewards lower param (more signals pass) → should pick 0.05
    result = retune(
        param_grid=[0.05, 0.08, 0.10],
        resolved_trades=[{"value": 0.07}] * 10,
        validate_fn=_score,
        max_step=0.10,
        current_value=0.08,
    )
    assert result == pytest.approx(0.05)


def test_never_uses_in_sample_data():
    # All training data has value=0.2, validation data has value=0.06
    # param 0.05 should score well on validation (0.06 > 0.05 = 1 match per trade)
    # param 0.08 scores 0 on validation (0.06 < 0.08)
    trades = [{"value": 0.2}] * 6 + [{"value": 0.06}] * 4
    result = retune(
        param_grid=[0.05, 0.08],
        resolved_trades=trades,
        validate_fn=_score,
        max_step=0.10,
        current_value=0.08,
    )
    # validation window is trades[6:] = 4 trades with value=0.06
    # 0.05 scores 4, 0.08 scores 0 → should pick 0.05
    assert result == pytest.approx(0.05)
