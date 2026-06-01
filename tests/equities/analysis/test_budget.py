import pytest
from equities.analysis.budget import DailyBudget


def test_allows_within_limit():
    b = DailyBudget(daily_limit_usd=1.0)
    assert b.allow(0.50) is True


def test_blocks_over_limit():
    b = DailyBudget(daily_limit_usd=1.0)
    b.record(0.90)
    assert b.allow(0.20) is False


def test_allows_exactly_at_limit():
    b = DailyBudget(daily_limit_usd=1.0)
    b.record(0.70)
    assert b.allow(0.30) is True


def test_spent_today_tracks_correctly():
    b = DailyBudget(daily_limit_usd=5.0)
    b.record(0.10)
    b.record(0.25)
    assert b.spent_today() == pytest.approx(0.35)


def test_resets_on_new_day(monkeypatch):
    from equities.analysis import budget as bmod
    b = DailyBudget(daily_limit_usd=0.50)
    b.record(0.40)
    assert b.allow(0.20) is False
    monkeypatch.setattr(bmod, "_today", lambda: "2030-01-02")
    assert b.allow(0.50) is True
