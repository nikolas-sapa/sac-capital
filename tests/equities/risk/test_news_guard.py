"""Tests for NewsGuard (equities/risk/news_guard.py)."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from equities.risk.news_guard import MacroEvent, NewsGuard


class _StubProvider:
    def __init__(self, events: list[MacroEvent]) -> None:
        self._events = events

    def fetch(self) -> list[MacroEvent]:
        return self._events


class _EmptyProvider:
    def fetch(self) -> list[MacroEvent]:
        return []


_FOMC = MacroEvent("FOMC Rate Decision", "FOMC", datetime(2026, 7, 29, 18, 0, tzinfo=UTC))


def test_blocks_inside_window():
    guard = NewsGuard(live_provider=_StubProvider([_FOMC]))
    result = guard.evaluate("AAPL", datetime(2026, 7, 29, 17, 0, tzinfo=UTC))
    assert result["decision"] == "block"
    assert result["reason"].startswith("FOMC_blackout")


def test_approves_outside_window():
    guard = NewsGuard(live_provider=_StubProvider([_FOMC]))
    result = guard.evaluate("AAPL", datetime(2026, 7, 24, 12, 0, tzinfo=UTC))
    assert result["decision"] == "approve"


def test_fails_closed_on_missing_data():
    guard = NewsGuard(live_provider=_EmptyProvider(), fallback_path=Path("/nonexistent/none.csv"))
    result = guard.evaluate("AAPL", datetime(2026, 7, 29, 17, 0, tzinfo=UTC))
    assert result["decision"] == "block"
    assert result["reason"] == "no_calendar_data_fail_closed"


def test_disabled_always_approves():
    guard = NewsGuard(enabled=False, live_provider=_StubProvider([_FOMC]))
    result = guard.evaluate("AAPL", datetime(2026, 7, 29, 18, 0, tzinfo=UTC))
    assert result["decision"] == "approve"
    assert result["reason"] == "news_blackout_disabled"


def test_naive_timestamp_rejected():
    guard = NewsGuard(live_provider=_StubProvider([_FOMC]))
    try:
        guard.evaluate("AAPL", datetime(2026, 7, 29, 17, 0))  # no tzinfo
        raise AssertionError("expected ValueError for naive timestamp")
    except ValueError:
        pass


def test_exits_module_never_imports_news_guard():
    """News blackout must gate new entries only — never exits/stops/trailing."""
    import equities.risk.exits as exits_mod
    assert not hasattr(exits_mod, "NewsGuard")


def test_real_bundled_csv_blocks_around_fomc():
    """Exercise the actual macro_events_fallback.csv (not a stub) — parse,
    ET->UTC DST conversion, and the blackout window all on real data."""
    guard = NewsGuard(live_provider=_EmptyProvider())
    result = guard.evaluate("AAPL", datetime(2026, 7, 29, 17, 0, tzinfo=UTC))  # 1h before 14:00 ET FOMC
    assert result["decision"] == "block"
    assert result["reason"].startswith("FOMC_blackout")


def test_real_bundled_csv_approves_quiet_day():
    guard = NewsGuard(live_provider=_EmptyProvider())
    result = guard.evaluate("AAPL", datetime(2026, 7, 20, 17, 0, tzinfo=UTC))
    assert result["decision"] == "approve"
    assert result["next_event"] is not None


def test_real_bundled_csv_fails_closed_outside_coverage():
    guard = NewsGuard(live_provider=_EmptyProvider())
    result = guard.evaluate("AAPL", datetime(2027, 1, 15, 17, 0, tzinfo=UTC))
    assert result["decision"] == "block"
    assert result["reason"] == "fallback_coverage_gap_fail_closed"
