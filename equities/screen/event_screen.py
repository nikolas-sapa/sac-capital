"""07b — Event-based screener for the swing sleeve.

Screens for *upcoming or recent events* that may cause a re-rating, NOT for
stocks that have already moved. Claude is the analyst; this is the cheap funnel.

Events detected (in urgency order):
1. EARNINGS_APPROACHING — next earnings date within `earnings_window_days`
2. EARNINGS_SURPRISE_DRIFT — 8-K item 2.02 filed within `filing_window_days`
   (post-earnings-announcement drift window)
3. MATERIAL_FILING — fresh 8-K with material items (1.01 / 5.02 / 8.01 / 7.01)
   within `filing_window_days`
4. ACTIVIST_13D — SC 13D / 13D-A filed within ~14 calendar days (activist
   stake disclosed; strongest still-alive event edge, Brav et al. 2008)

Only SMALL and MID cap instruments are eligible (configurable via `cap_tiers`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Protocol

from core.assets.instrument import CapTier, Instrument


class EventType(Enum):
    EARNINGS_APPROACHING = "earnings_approaching"
    EARNINGS_SURPRISE_DRIFT = "earnings_surprise_drift"
    MATERIAL_FILING = "material_filing"
    POLITICIAN_DISCLOSURE = "politician_disclosure"
    ACTIVIST_13D = "activist_13d"


@dataclass(frozen=True)
class CandidateEvent:
    instrument: Instrument
    event_type: EventType
    evidence: str
    urgency: float              # 0.0–1.0; higher = review sooner
    days_to_event: int | None = None


# ---------------------------------------------------------------------------
# Injectable provider protocols (real implementations live in equities/data/)
# ---------------------------------------------------------------------------

class EarningsDateProvider(Protocol):
    def next_date(self, ticker: str) -> date | None: ...


class FilingsProvider(Protocol):
    def recent_8k_items(self, ticker: str, days: int) -> list[tuple[date, list[str]]]:
        """Return list of (filed_date, item_codes) for recent 8-Ks."""
        ...

    def recent_activist_filings(self, ticker: str, days: int) -> list[tuple[date, str]]:
        """Return list of (filed_date, form_type) for recent SC 13D / SC 13D/A filings."""
        ...


# ---------------------------------------------------------------------------
# Adapters that wrap the richer data clients
# ---------------------------------------------------------------------------

class CalendarAdapter:
    """Wraps YFinanceCalendar to satisfy EarningsDateProvider."""

    def __init__(self, calendar: object, failure_callback=None) -> None:
        self._cal = calendar
        self._failure_callback = failure_callback

    def next_date(self, ticker: str) -> date | None:
        try:
            snap = self._cal.fetch(ticker)  # type: ignore[attr-defined]
            return snap.next_earnings_date
        except Exception as exc:
            print(f"  [PROVIDER] source=yfinance_calendar ticker={ticker} error={exc}")
            if self._failure_callback is not None:
                self._failure_callback()
            return None


class FilingsAdapter:
    """Wraps SECEdgarFilings to satisfy FilingsProvider."""

    def __init__(self, client: object, failure_callback=None) -> None:
        self._client = client
        self._failure_callback = failure_callback

    def recent_8k_items(self, ticker: str, days: int) -> list[tuple[date, list[str]]]:
        try:
            filings = self._client.recent(ticker, days=days)  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"  [PROVIDER] source=sec_filings ticker={ticker} error={exc}")
            if self._failure_callback is not None:
                self._failure_callback()
            return []
        return [
            (f.filed_date, f.items)
            for f in filings
            if f.form_type == "8-K"
        ]

    def recent_activist_filings(self, ticker: str, days: int) -> list[tuple[date, str]]:
        try:
            filings = self._client.recent(ticker, days=days)  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"  [PROVIDER] source=sec_filings ticker={ticker} error={exc}")
            if self._failure_callback is not None:
                self._failure_callback()
            return []
        return [
            (f.filed_date, f.form_type)
            for f in filings
            if f.form_type.startswith("SC 13D")
        ]


# ---------------------------------------------------------------------------
# Material item codes that warrant flagging (non-earnings)
# ---------------------------------------------------------------------------

_MATERIAL_ITEMS = frozenset({"1.01", "5.02", "8.01", "7.01", "1.02", "2.01"})

# SC 13D / 13D-A window: ~10 trading sessions (Brav et al. 2008 — abnormal
# return clusters in the days around filing, no reversal).
_ACTIVIST_FILING_WINDOW_DAYS = 14


class EventScreen:
    """Scan a universe of Instruments for upcoming catalyst events.

    Args:
        earnings:              Provider of next-earnings dates.
        filings:               Provider of recent 8-K item codes.
        earnings_window_days:  Flag if earnings ≤ N days away (default 14).
        filing_window_days:    Look back N days for fresh filings (default 10).
        cap_tiers:             Eligible cap tiers (default SMALL + MID).
    """

    def __init__(
        self,
        earnings: EarningsDateProvider,
        filings: FilingsProvider,
        earnings_window_days: int = 14,
        filing_window_days: int = 10,
        cap_tiers: set[CapTier] | None = None,
    ) -> None:
        self._earnings = earnings
        self._filings = filings
        self._earn_window = earnings_window_days
        self._file_window = filing_window_days
        self._cap_tiers = cap_tiers if cap_tiers is not None else {CapTier.SMALL, CapTier.MID}

    def scan(self, universe: list[Instrument]) -> list[CandidateEvent]:
        """Return CandidateEvents for all instruments that match an event filter.

        Results are sorted by urgency descending.
        """
        today = date.today()
        candidates: list[CandidateEvent] = []

        for inst in universe:
            if inst.cap_tier not in self._cap_tiers:
                continue

            candidates.extend(self._check_earnings(inst, today))
            candidates.extend(self._check_filings(inst, today))
            candidates.extend(self._check_activist_13d(inst, today))

        candidates.sort(key=lambda c: c.urgency, reverse=True)
        return candidates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_earnings(
        self, inst: Instrument, today: date
    ) -> list[CandidateEvent]:
        next_date = self._earnings.next_date(inst.ticker)
        if next_date is None:
            return []
        days_to = (next_date - today).days
        if not (0 <= days_to <= self._earn_window):
            return []
        urgency = 1.0 - days_to / self._earn_window if self._earn_window > 0 else 1.0
        return [
            CandidateEvent(
                instrument=inst,
                event_type=EventType.EARNINGS_APPROACHING,
                evidence=f"Earnings in {days_to}d ({next_date.isoformat()})",
                urgency=round(urgency, 4),
                days_to_event=days_to,
            )
        ]

    def _check_filings(
        self, inst: Instrument, today: date
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        filings = self._filings.recent_8k_items(inst.ticker, self._file_window)

        for filed_date, items in filings:
            days_ago = (today - filed_date).days
            if days_ago < 0 or days_ago > self._file_window:
                continue
            base_urgency = max(0.0, 1.0 - days_ago / self._file_window) if self._file_window > 0 else 1.0

            if "2.02" in items:
                events.append(
                    CandidateEvent(
                        instrument=inst,
                        event_type=EventType.EARNINGS_SURPRISE_DRIFT,
                        evidence=f"8-K item 2.02 (earnings) filed {days_ago}d ago ({filed_date})",
                        urgency=round(base_urgency, 4),
                    )
                )
            if _MATERIAL_ITEMS.intersection(items):
                matched = sorted(_MATERIAL_ITEMS.intersection(items))
                events.append(
                    CandidateEvent(
                        instrument=inst,
                        event_type=EventType.MATERIAL_FILING,
                        evidence=f"8-K items [{', '.join(matched)}] filed {days_ago}d ago",
                        urgency=round(base_urgency * 0.8, 4),  # slightly lower than earnings
                    )
                )

        return events

    def _check_activist_13d(
        self, inst: Instrument, today: date
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        filings = self._filings.recent_activist_filings(
            inst.ticker, _ACTIVIST_FILING_WINDOW_DAYS
        )

        for filed_date, form_type in filings:
            age_days = (today - filed_date).days
            if age_days < 0 or age_days > _ACTIVIST_FILING_WINDOW_DAYS:
                continue
            events.append(
                CandidateEvent(
                    instrument=inst,
                    event_type=EventType.ACTIVIST_13D,
                    evidence=(
                        f"{form_type} filed {filed_date.isoformat()}"
                        " — activist stake disclosed"
                    ),
                    urgency=1.0,
                    days_to_event=None,
                )
            )

        return events
