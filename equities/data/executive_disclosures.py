"""Executive-branch 278-T trades from Open Cabinet's reviewed JSON export.

Primary filings: U.S. Office of Government Ethics. Open Cabinet parses the
PDFs and publishes the structured export used here. Rows without tickers are
excluded; transaction dates are limited to the window preceding each
official's latest filing so older holdings are not resurfaced as new signals.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timezone

from equities.data.politician_disclosures import (
    DisclosureFetch,
    PoliticianTrade,
    parse_amount_range,
)

_DEFAULT_URL = "https://open-cabinet.org/data/full-dataset.json"
_PROFILE_URL = "https://open-cabinet.org/officials/{slug}"
_USER_AGENT = "sapa-fund-research/1.0 (paper-trading; public-disclosure research)"


def _fetch_bytes(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _date(raw: object) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _transaction_type(raw: object) -> str:
    value = str(raw or "").lower()
    if "purchase" in value:
        return "buy"
    if "sale" in value:
        return "sell"
    return "exchange"


class ExecutiveDisclosureProvider:
    """Fetch ticker-resolved executive trades. Never raises."""

    def __init__(
        self,
        *,
        url: str = _DEFAULT_URL,
        lookback_days: int = 45,
        timeout: float = 10.0,
    ) -> None:
        self._url = url
        self._lookback_days = lookback_days
        self._timeout = timeout

    def fetch(self) -> DisclosureFetch:
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = json.loads(_fetch_bytes(self._url, self._timeout))
            officials = payload.get("officials")
            if not isinstance(officials, list):
                raise ValueError("expected officials list")

            trades: list[PoliticianTrade] = []
            for official in officials:
                if not isinstance(official, dict):
                    continue
                filed = _date(official.get("mostRecentFilingDate"))
                slug = str(official.get("slug") or "").strip()
                if filed is None or not slug:
                    continue
                for raw in official.get("transactions") or []:
                    if not isinstance(raw, dict):
                        continue
                    ticker = str(raw.get("ticker") or "").strip().upper()
                    transacted = _date(raw.get("date"))
                    if not ticker or transacted is None:
                        continue
                    lag = (filed - transacted).days
                    if lag < 0 or lag > self._lookback_days:
                        continue
                    amount_min, amount_max = parse_amount_range(raw.get("amount"))
                    trades.append(PoliticianTrade(
                        ticker=ticker,
                        politician=str(official.get("name") or "unknown").strip(),
                        chamber="executive",
                        transaction_type=_transaction_type(raw.get("type")),
                        owner="self",
                        amount_min=amount_min,
                        amount_max=amount_max,
                        transaction_date=transacted,
                        date_filed=filed,
                        filing_lag_days=lag,
                        source="open_cabinet",
                        source_url=_PROFILE_URL.format(slug=slug),
                    ))
            return DisclosureFetch(
                trades=trades,
                fetched_at=fetched_at,
                source="open_cabinet",
                error=None,
            )
        except Exception as exc:
            return DisclosureFetch(
                trades=[],
                fetched_at=fetched_at,
                source="open_cabinet",
                error=f"open_cabinet: {exc}",
            )
