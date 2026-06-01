from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Protocol, runtime_checkable


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
    _SEARCH = "https://efts.sec.gov/LATEST/search-index"

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
        import httpx

        try:
            resp = httpx.get(
                f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=8-K&dateRange=custom&startdt=2020-01-01&enddt=2020-12-31",
                headers={"User-Agent": "polymarket-bot research@example.com"},
                timeout=10,
            )
            # Prefer the company search endpoint
            search = httpx.get(
                f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=10-K",
                headers={"User-Agent": "polymarket-bot research@example.com"},
                timeout=10,
            )
            hits = search.json().get("hits", {}).get("hits", [])
            if hits:
                return int(hits[0]["_source"].get("entity_id", 0)) or None
        except Exception:
            pass

        # Fallback: company-ticker.json lookup
        try:
            resp = httpx.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": "polymarket-bot research@example.com"},
                timeout=15,
            )
            for entry in resp.json().values():
                if entry.get("ticker", "").upper() == ticker.upper():
                    return int(entry["cik_str"])
        except Exception:
            pass
        return None
