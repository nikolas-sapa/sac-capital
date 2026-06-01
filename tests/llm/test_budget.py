from datetime import date

from strategies.llm_probability.budget import DailyBudget


def test_allow_under_limit():
    b = DailyBudget(limit_usd=1.0)
    assert b.allow(0.30) is True


def test_allow_at_limit_boundary():
    b = DailyBudget(limit_usd=1.0)
    b.record(0.70)
    assert b.allow(0.30) is True   # would hit exactly 1.0 — still allowed


def test_deny_over_limit():
    b = DailyBudget(limit_usd=1.0)
    b.record(0.80)
    assert b.allow(0.30) is False  # 0.80 + 0.30 = 1.10 > 1.0


def test_record_accumulates():
    b = DailyBudget(limit_usd=5.0)
    b.record(0.50)
    b.record(0.50)
    assert b.spent_today() == 1.0


def test_resets_on_new_day(monkeypatch):
    import strategies.llm_probability.budget as mod
    b = DailyBudget(limit_usd=0.10)
    b.record(0.10)
    assert b.allow(0.01) is False

    # Advance the clock to tomorrow
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    monkeypatch.setattr(mod, "_today", lambda: tomorrow)
    assert b.allow(0.01) is True
