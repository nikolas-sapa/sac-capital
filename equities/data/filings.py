from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Protocol, runtime_checkable


_USER_AGENT = "polymarket-bot research@example.com"


@dataclass(frozen=True)
class Filing:
    form_type: str      # "8-K", "10-Q", "10-K"
    filed_date: date
    items: list[str]    # e.g. ["2.02", "9.01"] for earnings-results 8-K


@runtime_checkable
class FilingsClient(Protocol):
    def recent(self, ticker: str, days: int = 30) -> list[Filing]: ...


class SECEdgarFilings:
    """Fetch recent SEC filings from the free EDGAR public API."""

    _BASE = "https://efts.sec.gov"
    _SUBMISSIONS = "https://data.sec.gov/submissions"
    _TICKERS = "https://www.sec.gov/files/company_tickers.json"

    def recent(self, ticker: str, days: int = 30) -> list[Filing]:
        import httpx

        cik = self._cik(ticker)
        if not cik:
            return []

        padded = str(cik).zfill(10)
        try:
            resp = httpx.get(
                f"{self._SUBMISSIONS}/CIK{padded}.json",
                headers={"User-Agent": "polymarket-bot research@example.com"},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            return []

        data = resp.json()
        recent_data = data.get("filings", {}).get("recent", {})
        forms = recent_data.get("form", [])
        dates = recent_data.get("filingDate", [])
        items_raw = recent_data.get("items", [])

        cutoff = date.today() - timedelta(days=days)
        result: list[Filing] = []

        for form, dt_str, item_str in zip(forms, dates, items_raw):
            try:
                filed = date.fromisoformat(dt_str)
            except (ValueError, TypeError):
                continue
            if filed < cutoff:
                break  # EDGAR returns newest-first; stop when older than cutoff
            if form not in ("8-K", "10-Q", "10-K"):
                continue
            items = [i.strip() for i in (item_str or "").split(",") if i.strip()]
            result.append(Filing(form_type=form, filed_date=filed, items=items))

        return result

    def _cik(self, ticker: str) -> int | None:
        return _ticker_to_cik(ticker)


@lru_cache(maxsize=1)
def _company_ticker_map() -> dict[str, int]:
    import httpx

    try:
        resp = httpx.get(
            SECEdgarFilings._TICKERS,
            headers={"User-Agent": _USER_AGENT},
            timeout=httpx.Timeout(5.0, connect=2.0, read=3.0, write=2.0, pool=2.0),
        )
        resp.raise_for_status()
        mapping: dict[str, int] = {}
        for entry in resp.json().values():
            ticker = str(entry.get("ticker", "")).upper().strip()
            cik = int(entry.get("cik_str", 0) or 0)
            if ticker and cik:
                mapping[ticker] = cik
        return mapping
    except Exception:
        return {}


@lru_cache(maxsize=2048)
def _ticker_to_cik(ticker: str) -> int | None:
    return _company_ticker_map().get(ticker.upper().strip())
