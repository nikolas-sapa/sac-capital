from datetime import datetime, timezone, timedelta

import pytest

from equities.risk.exits import ExitSignal, check_exit


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def test_stop_hit_when_price_at_stop():
    opened = _now() - timedelta(days=1)
    result = check_exit(1, current_price=44.0, stop_loss=45.0, take_profit=60.0,
                        opened_at=opened, current_time=_now())
    assert result is not None
    assert result.reason == "stop_hit"


def test_no_stop_when_price_above():
    opened = _now() - timedelta(days=1)
    result = check_exit(1, current_price=50.0, stop_loss=45.0, take_profit=60.0,
                        opened_at=opened, current_time=_now())
    assert result is None


def test_target_hit():
    opened = _now() - timedelta(days=1)
    result = check_exit(1, current_price=61.0, stop_loss=45.0, take_profit=60.0,
                        opened_at=opened, current_time=_now())
    assert result is not None
    assert result.reason == "target_hit"


def test_time_stop_after_max_days():
    opened = _now() - timedelta(days=22)
    result = check_exit(1, current_price=52.0, stop_loss=45.0, take_profit=60.0,
                        opened_at=opened, current_time=_now(), max_days=21)
    assert result is not None
    assert result.reason == "time_stop"


def test_no_time_stop_before_max_days():
    opened = _now() - timedelta(days=10)
    result = check_exit(1, current_price=52.0, stop_loss=45.0, take_profit=60.0,
                        opened_at=opened, current_time=_now(), max_days=21)
    assert result is None


def test_none_stop_loss_not_triggered():
    opened = _now() - timedelta(days=1)
    result = check_exit(1, current_price=30.0, stop_loss=None, take_profit=None,
                        opened_at=opened, current_time=_now())
    assert result is None  # no stop, no target, not timed out yet


def test_stop_hit_returns_correct_exit_price():
    opened = _now() - timedelta(days=1)
    result = check_exit(7, current_price=43.5, stop_loss=44.0, take_profit=60.0,
                        opened_at=opened, current_time=_now())
    assert result is not None
    assert result.position_id == 7
    assert result.exit_price == pytest.approx(43.5)
