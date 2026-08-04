from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Protocol, runtime_checkable


# SEC fair-access policy wants a real declaring contact. Override via .env;
# the fallback is deliberately generic so no personal address is committed.
_USER_AGENT = os.getenv("SEC_USER_AGENT", "sac-capital research contact@example.com")
_SUBMISSIONS_TIMEOUT = 10.0  # HTTP timeout for SEC EDGAR submissions API
_TICKERS_TIMEOUT = 5.0  # HTTP timeout for SEC ticker mapping (cached)
_logger = logging.getLogger(__name__)


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
            print(f"  [PROVIDER] source=sec_filings ticker={ticker} error=no_cik_mapping")
            return []

        padded = str(cik).zfill(10)
        try:
            resp = httpx.get(
                f"{self._SUBMISSIONS}/CIK{padded}.json",
                headers={"User-Agent": _USER_AGENT},
                timeout=_SUBMISSIONS_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.TimeoutException:
            print(f"  [PROVIDER] source=sec_filings ticker={ticker} error=timeout")
            _logger.warning(f"Timeout fetching SEC filings for {ticker} (CIK {cik}); returning empty list")
            return []
        except Exception as exc:
            print(f"  [PROVIDER] source=sec_filings ticker={ticker} error={type(exc).__name__}: {exc}")
            return []

        data = resp.json()
        recent_data = data.get("filings", {}).get("recent", {})
        forms = recent_data.get("form", [])
        dates = recent_data.get("filingDate", [])
        items_raw = recent_data.get("items", [])

        cutoff = date.today() - timedelta(days=days)
        result: list[Filing] = []

        # Guard against mismatched list lengths
        if len(forms) != len(dates) or len(dates) != len(items_raw):
            print(
                f"  [PROVIDER] source=sec_filings ticker={ticker} "
                f"warning=mismatched_lengths forms={len(forms)} dates={len(dates)} items={len(items_raw)}"
            )

        for form, dt_str, item_str in zip(forms, dates, items_raw):
            try:
                filed = date.fromisoformat(dt_str)
            except (ValueError, TypeError):
                continue
            if filed < cutoff:
                break  # EDGAR returns newest-first; stop when older than cutoff
            if form not in ("8-K", "10-Q", "10-K", "SC 13D", "SC 13D/A"):
                continue
            items = [i.strip() for i in (item_str or "").split(",") if i.strip()]
            result.append(Filing(form_type=form, filed_date=filed, items=items))

        return result

    def _cik(self, ticker: str) -> int | None:
        return _ticker_to_cik(ticker)


# ponytail: hand-rolled cache instead of @lru_cache because a failed fetch must
# NOT be cached — lru_cache pinned an empty map for the whole run and silently
# blinded every filings-based screen (provider_failures stayed 0).
_TICKER_MAP_CACHE: dict[str, int] = {}


def _company_ticker_map() -> dict[str, int]:
    import httpx

    if _TICKER_MAP_CACHE:
        return _TICKER_MAP_CACHE

    try:
        resp = httpx.get(
            SECEdgarFilings._TICKERS,
            headers={"User-Agent": _USER_AGENT},
            timeout=httpx.Timeout(_TICKERS_TIMEOUT, connect=2.0, read=3.0, write=2.0, pool=2.0),
        )
        resp.raise_for_status()
        mapping: dict[str, int] = {}
        for entry in resp.json().values():
            ticker = str(entry.get("ticker", "")).upper().strip()
            cik = int(entry.get("cik_str", 0) or 0)
            if ticker and cik:
                mapping[ticker] = cik
    except Exception as exc:
        # Loud: an empty map disables every filings screen, so it must never
        # look like "no filings found".
        print(f"  [PROVIDER] source=sec_ticker_map error={type(exc).__name__}: {exc}")
        _logger.warning("SEC ticker map fetch failed (%s); filings screens degraded", exc)
        return {}

    if not mapping:
        print("  [PROVIDER] source=sec_ticker_map error=empty_mapping")
        return {}

    _TICKER_MAP_CACHE.update(mapping)
    return _TICKER_MAP_CACHE


def _ticker_to_cik(ticker: str) -> int | None:
    return _company_ticker_map().get(ticker.upper().strip())
