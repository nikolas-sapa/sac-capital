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


import json
from datetime import date

from equities.risk.exits import _horizon_days, evaluate_exit


def _pos(**kw):
    base = dict(
        id=1, entry_price=100.0, stop_loss=90.0, take_profit=120.0,
        high_water_price=None, opened_at="2026-07-01T00:00:00+00:00",
        analysis_json=json.dumps({"horizon": "3-4 weeks"}),
    )
    base.update(kw)
    return base


def test_horizon_days_parsing():
    assert _horizon_days("1-2 weeks") == 14
    assert _horizon_days("10 days") == 10
    assert _horizon_days("3 months") == 90
    assert _horizon_days("gibberish") == 21
    assert _horizon_days(None) == 21


def test_hard_stop_still_fires():
    sig = evaluate_exit(_pos(), current_price=89.0, today=date(2026, 7, 5))
    assert sig is not None and sig.reason == "stop_hit"


def test_target_touch_no_longer_exits():
    # price above take_profit: old engine exited; new engine holds (trail active)
    sig = evaluate_exit(_pos(high_water_price=121.0), current_price=121.0,
                        today=date(2026, 7, 5))
    assert sig is None


def test_breakeven_ratchet_after_one_r():
    # R = 10. high water 111 (>= entry + 1R) ratchets stop to entry (100).
    sig = evaluate_exit(_pos(high_water_price=111.0), current_price=99.0,
                        today=date(2026, 7, 5))
    assert sig is not None and sig.reason == "trailing_stop_hit"
    # ...but a price above entry holds
    assert evaluate_exit(_pos(high_water_price=111.0), current_price=101.0,
                         today=date(2026, 7, 5)) is None


def test_r_trail_after_target_activation():
    # R = 10, trail_r = 1.5 -> trail distance 15. HW 130 -> trail stop 115.
    pos = _pos(high_water_price=130.0)
    sig = evaluate_exit(pos, current_price=114.0, today=date(2026, 7, 5))
    assert sig is not None and sig.reason == "trailing_stop_hit"
    assert evaluate_exit(pos, current_price=116.0, today=date(2026, 7, 5)) is None


def test_horizon_time_stop():
    # horizon "3-4 weeks" = 28 days from 2026-07-01 -> fires on day 29+
    assert evaluate_exit(_pos(), current_price=105.0, today=date(2026, 7, 20)) is None
    sig = evaluate_exit(_pos(), current_price=105.0, today=date(2026, 7, 30))
    assert sig is not None and sig.reason == "time_stop"


def test_dca_sleeve_skips_price_exits():
    # CORE: no stop, no target — nothing fires (no time stop for core either)
    pos = _pos(stop_loss=None, take_profit=None,
               analysis_json=json.dumps({}))
    assert evaluate_exit(pos, current_price=1.0, today=date(2027, 7, 5)) is None
