"""Tests for the event-based swing screener (07b)."""
from datetime import date, timedelta

import pytest

from core.assets.instrument import CapTier, Instrument
from equities.screen.event_screen import (
    CandidateEvent,
    EventScreen,
    EventType,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeEarnings:
    def __init__(self, dates: dict[str, date | None] | None = None):
        self._dates = dates or {}

    def next_date(self, ticker: str) -> date | None:
        return self._dates.get(ticker)


class FakeFilings:
    def __init__(self, data: dict[str, list[tuple[date, list[str]]]] | None = None):
        self._data = data or {}

    def recent_8k_items(self, ticker: str, days: int) -> list[tuple[date, list[str]]]:
        return self._data.get(ticker, [])


def _inst(ticker: str, cap: CapTier = CapTier.SMALL) -> Instrument:
    return Instrument(ticker=ticker, name=ticker, exchange="NASDAQ", cap_tier=cap)


def _today(offset: int = 0) -> date:
    return date.today() + timedelta(days=offset)


# ---------------------------------------------------------------------------
# Earnings approaching tests
# ---------------------------------------------------------------------------

def test_earnings_in_window_flagged():
    inst = _inst("PGNY")
    screen = EventScreen(
        earnings=FakeEarnings({"PGNY": _today(7)}),
        filings=FakeFilings(),
        earnings_window_days=14,
    )
    results = screen.scan([inst])
    assert len(results) == 1
    assert results[0].event_type == EventType.EARNINGS_APPROACHING
    assert results[0].days_to_event == 7


def test_earnings_outside_window_not_flagged():
    inst = _inst("X")
    screen = EventScreen(
        earnings=FakeEarnings({"X": _today(20)}),
        filings=FakeFilings(),
        earnings_window_days=14,
    )
    assert screen.scan([inst]) == []


def test_earnings_today_max_urgency():
    inst = _inst("Y")
    screen = EventScreen(
        earnings=FakeEarnings({"Y": _today(0)}),
        filings=FakeFilings(),
        earnings_window_days=14,
    )
    results = screen.scan([inst])
    assert len(results) == 1
    assert results[0].urgency == pytest.approx(1.0)


def test_no_earnings_date_no_event():
    inst = _inst("Z")
    screen = EventScreen(
        earnings=FakeEarnings({"Z": None}),
        filings=FakeFilings(),
    )
    assert screen.scan([inst]) == []


# ---------------------------------------------------------------------------
# PEAD / earnings surprise drift tests
# ---------------------------------------------------------------------------

def test_recent_earnings_filing_flagged():
    inst = _inst("ARWR")
    screen = EventScreen(
        earnings=FakeEarnings(),
        filings=FakeFilings({"ARWR": [(_today(-3), ["2.02", "9.01"])]}),
        filing_window_days=10,
    )
    results = screen.scan([inst])
    assert any(r.event_type == EventType.EARNINGS_SURPRISE_DRIFT for r in results)


def test_stale_earnings_filing_not_flagged():
    inst = _inst("A")
    screen = EventScreen(
        earnings=FakeEarnings(),
        filings=FakeFilings({"A": [(_today(-15), ["2.02"])]}),
        filing_window_days=10,
    )
    assert screen.scan([inst]) == []


# ---------------------------------------------------------------------------
# Material filing tests
# ---------------------------------------------------------------------------

def test_material_filing_items_flagged():
    inst = _inst("PRCT")
    screen = EventScreen(
        earnings=FakeEarnings(),
        filings=FakeFilings({"PRCT": [(_today(-2), ["5.02", "9.01"])]}),
        filing_window_days=10,
    )
    results = screen.scan([inst])
    assert any(r.event_type == EventType.MATERIAL_FILING for r in results)


def test_routine_filing_not_flagged():
    inst = _inst("B")
    screen = EventScreen(
        earnings=FakeEarnings(),
        filings=FakeFilings({"B": [(_today(-1), ["9.01"])]}),
        filing_window_days=10,
    )
    # 9.01 alone is not in _MATERIAL_ITEMS
    assert screen.scan([inst]) == []


# ---------------------------------------------------------------------------
# Cap tier filter tests
# ---------------------------------------------------------------------------

def test_large_cap_excluded_from_swing_screen():
    inst = _inst("SPY", cap=CapTier.LARGE)
    screen = EventScreen(
        earnings=FakeEarnings({"SPY": _today(5)}),
        filings=FakeFilings(),
    )
    assert screen.scan([inst]) == []


def test_large_cap_included_when_configured():
    inst = _inst("AAPL", cap=CapTier.LARGE)
    screen = EventScreen(
        earnings=FakeEarnings({"AAPL": _today(5)}),
        filings=FakeFilings(),
        cap_tiers={CapTier.LARGE},
    )
    results = screen.scan([inst])
    assert len(results) == 1


def test_mid_cap_included_by_default():
    inst = _inst("MID", cap=CapTier.MID)
    screen = EventScreen(
        earnings=FakeEarnings({"MID": _today(3)}),
        filings=FakeFilings(),
    )
    assert len(screen.scan([inst])) == 1


# ---------------------------------------------------------------------------
# Ordering test
# ---------------------------------------------------------------------------

def test_results_sorted_by_urgency_descending():
    insts = [_inst("A"), _inst("B")]
    screen = EventScreen(
        earnings=FakeEarnings({"A": _today(12), "B": _today(1)}),
        filings=FakeFilings(),
        earnings_window_days=14,
    )
    results = screen.scan(insts)
    urgencies = [r.urgency for r in results]
    assert urgencies == sorted(urgencies, reverse=True)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_satisfies_result_protocol():
    from equities.screen.event_screen import CandidateEvent, EventType
    from core.assets.instrument import Instrument, CapTier
    c = CandidateEvent(
        instrument=_inst("X"),
        event_type=EventType.EARNINGS_APPROACHING,
        evidence="test",
        urgency=0.5,
        days_to_event=7,
    )
    assert hasattr(c, "instrument")
    assert hasattr(c, "urgency")
