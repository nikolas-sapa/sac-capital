from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from equities.data.yfinance_utils import call_quietly


@dataclass(frozen=True)
class EarningsSnapshot:
    ticker: str
    next_earnings_date: date | None
    last_surprise_pct: float | None  # positive = beat, negative = miss


@runtime_checkable
class EarningsCalendar(Protocol):
    def fetch(self, ticker: str) -> EarningsSnapshot: ...


class YFinanceCalendar:
    """Fetch upcoming earnings date and last surprise via yfinance."""

    def fetch(self, ticker: str) -> EarningsSnapshot:
        import yfinance as yf

        t = call_quietly(lambda: yf.Ticker(ticker))
        next_date = self._next_date(t)
        last_surprise = self._last_surprise(t)
        return EarningsSnapshot(
            ticker=ticker,
            next_earnings_date=next_date,
            last_surprise_pct=last_surprise,
        )

    def _next_date(self, t: object) -> date | None:
        try:
            cal = call_quietly(lambda: t.calendar)  # type: ignore[attr-defined]
            if cal is None:
                return None
            # yfinance ≥0.2: calendar is a dict with 'Earnings Date' key
            if isinstance(cal, dict):
                raw = cal.get("Earnings Date")
                if raw:
                    val = raw[0] if isinstance(raw, list) else raw
                    return _to_date(val)
            # older yfinance: DataFrame
            if hasattr(cal, "columns"):
                cols = [c for c in cal.columns if "Earnings" in str(c)]
                if cols:
                    val = cal[cols[0]].iloc[0]
                    return _to_date(val)
        except Exception:
            pass
        return None

    def _last_surprise(self, t: object) -> float | None:
        try:
            history = call_quietly(lambda: t.earnings_history)  # type: ignore[attr-defined]
            if history is not None and not history.empty:
                col = [c for c in history.columns if "surprise" in str(c).lower()]
                if col:
                    return float(history[col[0]].dropna().iloc[-1])
        except Exception:
            pass
        return None


def _to_date(val: object) -> date | None:
    if val is None:
        return None
    if hasattr(val, "date"):
        return val.date()  # type: ignore[return-value]
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None
