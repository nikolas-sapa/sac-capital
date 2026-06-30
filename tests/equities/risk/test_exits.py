import pytest

from equities.risk.exits import ExitSignal, check_exit


def test_stop_hit_when_price_at_stop():
    result = check_exit(1, current_price=44.0, stop_loss=45.0, take_profit=60.0)
    assert result is not None
    assert result.reason == "stop_hit"


def test_no_stop_when_price_above():
    result = check_exit(1, current_price=50.0, stop_loss=45.0, take_profit=60.0)
    assert result is None


def test_target_hit():
    result = check_exit(1, current_price=61.0, stop_loss=45.0, take_profit=60.0)
    assert result is not None
    assert result.reason == "target_hit"


def test_no_exit_within_price_bounds():
    result = check_exit(1, current_price=52.0, stop_loss=45.0, take_profit=60.0)
    assert result is None


def test_none_stop_loss_not_triggered():
    result = check_exit(1, current_price=30.0, stop_loss=None, take_profit=None)
    assert result is None


def test_stop_hit_returns_correct_exit_price():
    result = check_exit(7, current_price=43.5, stop_loss=44.0, take_profit=60.0)
    assert result is not None
    assert result.position_id == 7
    assert result.exit_price == pytest.approx(43.5)
