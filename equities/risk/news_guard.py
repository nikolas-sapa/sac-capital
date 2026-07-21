"""Macro event blackout guard — blocks NEW equity entries near high-impact
US macro releases (FOMC, CPI, NFP).

Window defaults: 24h before / 2h after (NOT the classic 30min/15min intraday
window). This system holds daily-bar swing positions, not intraday
scalps — entering ANY time on FOMC/CPI/NFP day exposes the position to the
whole day's pre-positioning drift plus the post-release volatility spike
before the position has even printed a first close. 24h before covers the
prior session's pre-positioning through the event; 2h after covers the
initial algorithmic/press-conference reaction. Exits, stops and the
trailing/ratchet logic in equities/risk/exits.py are never touched by this
guard — it only gates the NEW-entry decision in runner_equities.py.

Data source priority:
  1. Live: ForexFactoryCalendar — free, keyless weekly JSON feed, refetched
     once per run and cached on the NewsGuard instance.
  2. Fallback: bundled CSV (macro_events_fallback.csv) — best-effort static
     FOMC/CPI/NFP dates for _FALLBACK_COVERAGE, used only when the live
     fetch returns nothing.
  3. Neither available for the query date -> FAIL CLOSED (block new
     entries). This guard must never silently fail open.

PIT note: FOMC/CPI/NFP dates are publicly pre-announced months in advance,
so evaluating against a future scheduled date is not look-ahead bias (unlike
e.g. an earnings-surprise number) — equities/pit.py's assert_point_in_time
is not applicable here, same as equities/data/vix.py's VIXRegimeGate.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

_logger = logging.getLogger(__name__)

_NY = ZoneInfo("America/New_York")
_FALLBACK_CSV = Path(__file__).parent / "macro_events_fallback.csv"
_FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_FETCH_TIMEOUT = 8.0

# The fallback CSV enumerates events only within this range. A query date
# outside this range means "we never attempted to cover this period" (not
# "no event exists") -> must fail closed, distinct from an empty result.
_FALLBACK_COVERAGE_START = date(2026, 1, 1)
_FALLBACK_COVERAGE_END = date(2026, 12, 31)

_DEFAULT_BEFORE_H = 24.0
_DEFAULT_AFTER_H = 2.0

_HIGH_IMPACT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "FOMC": ("fomc",),
    "CPI": ("cpi",),
    "NFP": ("non-farm", "nonfarm", "non farm payrolls"),
}

EventType = Literal["FOMC", "CPI", "NFP"]


@dataclass(frozen=True)
class MacroEvent:
    name: str
    event_type: EventType
    at_utc: datetime  # timezone-aware


@runtime_checkable
class MacroCalendarProvider(Protocol):
    def fetch(self) -> list[MacroEvent]: ...


class ForexFactoryCalendar:
    """Live source: free, keyless Forex Factory "this week" JSON calendar.

    Only covers roughly the current calendar week — that's fine, the runner
    only needs to check entries being placed *now*.
    """

    def fetch(self) -> list[MacroEvent]:
        import httpx

        try:
            resp = httpx.get(
                _FOREX_FACTORY_URL,
                timeout=_FETCH_TIMEOUT,
                headers={"User-Agent": "sapa-fund research"},
            )
            resp.raise_for_status()
            rows = resp.json()
        except Exception as exc:
            _logger.warning(f"  [PROVIDER] source=forex_factory_calendar error={exc}")
            return []

        events: list[MacroEvent] = []
        for row in rows:
            if row.get("country") != "USD" or row.get("impact") != "High":
                continue
            title = str(row.get("title", ""))
            event_type = _classify(title)
            if event_type is None:
                continue
            when = _parse_ff_datetime(row.get("date"))
            if when is None:
                continue
            events.append(MacroEvent(name=title, event_type=event_type, at_utc=when))
        return events


def _classify(title: str) -> EventType | None:
    low = title.lower()
    for event_type, keywords in _HIGH_IMPACT_KEYWORDS.items():
        if any(k in low for k in keywords):
            return event_type  # type: ignore[return-value]
    return None


def _parse_ff_datetime(raw: object) -> datetime | None:
    """Forex Factory 'date' field is ISO-8601 with an explicit UTC offset."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_NY)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _load_fallback_csv(path: Path) -> list[MacroEvent]:
    """Load the bundled best-effort FOMC/CPI/NFP schedule.

    CSV columns: event_type,name,date,time_et (date/time interpreted in
    America/New_York, DST-aware via zoneinfo).
    """
    if not path.exists():
        return []
    events: list[MacroEvent] = []
    try:
        with path.open(newline="") as f:
            lines = [ln for ln in f if not ln.lstrip().startswith("#")]
            reader = csv.DictReader(lines)
            for row in reader:
                try:
                    d = date.fromisoformat(row["date"])
                    hh, mm = (int(x) for x in row["time_et"].split(":"))
                    naive = datetime(d.year, d.month, d.day, hh, mm)
                    at_ny = naive.replace(tzinfo=_NY)
                    events.append(
                        MacroEvent(
                            name=row["name"],
                            event_type=row["event_type"],  # type: ignore[arg-type]
                            at_utc=at_ny.astimezone(timezone.utc),
                        )
                    )
                except (KeyError, ValueError) as exc:
                    _logger.warning(f"  [NEWS_GUARD] malformed fallback CSV row {row}: {exc}")
    except OSError as exc:
        _logger.warning(f"  [NEWS_GUARD] could not read fallback CSV {path}: {exc}")
        return []
    return events


def _in_coverage(d: date) -> bool:
    return _FALLBACK_COVERAGE_START <= d <= _FALLBACK_COVERAGE_END


class NewsGuard:
    """Given a symbol and timestamp, decide whether a NEW entry is allowed.

    Fails CLOSED (blocks) when neither the live calendar nor the bundled
    fallback can rule out a nearby high-impact event — never fails open.
    """

    def __init__(
        self,
        enabled: bool = True,
        before_hours: float = _DEFAULT_BEFORE_H,
        after_hours: float = _DEFAULT_AFTER_H,
        live_provider: MacroCalendarProvider | None = None,
        fallback_path: Path = _FALLBACK_CSV,
        failure_callback: Any = None,
    ) -> None:
        self._enabled = enabled
        self._before = timedelta(hours=before_hours)
        self._after = timedelta(hours=after_hours)
        self._live_provider = live_provider if live_provider is not None else ForexFactoryCalendar()
        self._fallback_path = fallback_path
        self._failure_callback = failure_callback
        self._events: list[MacroEvent] | None = None
        self._source: str = ""  # "live" | "fallback" | "none"

    def _load(self) -> None:
        if self._events is not None:
            return
        try:
            live_events = self._live_provider.fetch()
        except Exception as exc:
            _logger.warning(f"  [NEWS_GUARD] live provider raised: {exc}")
            live_events = []
        if live_events:
            self._events = live_events
            self._source = "live"
            return
        fallback_events = _load_fallback_csv(self._fallback_path)
        if fallback_events:
            self._events = fallback_events
            self._source = "fallback"
        else:
            self._events = []
            self._source = "none"
            _logger.error("  [NEWS_GUARD] no live calendar and no fallback data — failing CLOSED")
            if self._failure_callback is not None:
                self._failure_callback()

    def evaluate(self, symbol: str, at: datetime) -> dict[str, Any]:
        """Return {decision, reason, next_event, minutes_until} for a NEW
        entry in *symbol* at time *at* (tz-aware, any timezone)."""
        if at.tzinfo is None:
            raise ValueError("NewsGuard.evaluate() requires a timezone-aware timestamp")
        at_utc = at.astimezone(timezone.utc)

        if not self._enabled:
            return {"decision": "approve", "reason": "news_blackout_disabled", "next_event": None, "minutes_until": None}

        self._load()

        if self._source == "none":
            # Already logged once + counted as a provider failure in _load().
            return {"decision": "block", "reason": "no_calendar_data_fail_closed", "next_event": None, "minutes_until": None}

        if self._source == "fallback" and not _in_coverage(at_utc.date()):
            # A coverage gap is a policy decision (static data doesn't reach this
            # date), not a provider fetch error — logged but not counted against
            # the runner's provider-failure breaker.
            _logger.warning(f"  [NEWS_GUARD] fallback CSV does not cover {at_utc.date()} — failing CLOSED")
            return {"decision": "block", "reason": "fallback_coverage_gap_fail_closed", "next_event": None, "minutes_until": None}

        events = sorted(self._events or [], key=lambda e: e.at_utc)

        blocking = next(
            (e for e in events if (e.at_utc - self._before) <= at_utc <= (e.at_utc + self._after)),
            None,
        )
        if blocking is not None:
            minutes_until = round((blocking.at_utc - at_utc).total_seconds() / 60.0, 1)
            return {
                "decision": "block",
                "reason": f"{blocking.event_type}_blackout:{blocking.name}",
                "next_event": blocking.name,
                "minutes_until": minutes_until,
            }

        upcoming = next((e for e in events if e.at_utc >= at_utc), None)
        minutes_until = round((upcoming.at_utc - at_utc).total_seconds() / 60.0, 1) if upcoming else None
        return {
            "decision": "approve",
            "reason": "no_macro_event_in_window",
            "next_event": upcoming.name if upcoming else None,
            "minutes_until": minutes_until,
        }


if __name__ == "__main__":
    # Runnable self-check (also mirrored in tests/equities/test_news_guard.py).
    from datetime import UTC

    class _StubProvider:
        def __init__(self, events: list[MacroEvent]) -> None:
            self._events = events

        def fetch(self) -> list[MacroEvent]:
            return self._events

    class _EmptyProvider:
        def fetch(self) -> list[MacroEvent]:
            return []

    fomc = MacroEvent("FOMC Rate Decision", "FOMC", datetime(2026, 7, 29, 18, 0, tzinfo=UTC))

    # 1. Blocks inside the window (1h before the event).
    guard = NewsGuard(live_provider=_StubProvider([fomc]))
    r = guard.evaluate("AAPL", datetime(2026, 7, 29, 17, 0, tzinfo=UTC))
    assert r["decision"] == "block", r
    assert r["reason"].startswith("FOMC_blackout"), r

    # 2. Approves outside the window (5 days before).
    guard = NewsGuard(live_provider=_StubProvider([fomc]))
    r = guard.evaluate("AAPL", datetime(2026, 7, 24, 12, 0, tzinfo=UTC))
    assert r["decision"] == "approve", r

    # 3. Fails closed when there is no live data and fallback path is invalid.
    guard = NewsGuard(live_provider=_EmptyProvider(), fallback_path=Path("/nonexistent/none.csv"))
    r = guard.evaluate("AAPL", datetime(2026, 7, 29, 17, 0, tzinfo=UTC))
    assert r["decision"] == "block", r
    assert r["reason"] == "no_calendar_data_fail_closed", r

    # 4. Disabled flag always approves (config off-switch works).
    guard = NewsGuard(enabled=False, live_provider=_StubProvider([fomc]))
    r = guard.evaluate("AAPL", datetime(2026, 7, 29, 18, 0, tzinfo=UTC))
    assert r["decision"] == "approve", r
    assert r["reason"] == "news_blackout_disabled", r

    # 5. This guard is entry-only — equities/risk/exits.py never imports or
    #    calls NewsGuard, so exits/stops/trailing logic are structurally
    #    unaffected regardless of blackout state (see equities/risk/exits.py).
    import equities.risk.exits as exits_mod
    assert not hasattr(exits_mod, "NewsGuard")

    print("news_guard self-check: OK (5/5 assertions passed)")
