"""Politician STOCK Act disclosure signals — House + Senate public filings.

Source (slice 1): pre-parsed public JSON mirrors of official STOCK Act filings.
  house  : https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json
  senate : https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json
Both fetches are independent; partial results are valid. Never raises — all
errors surface in DisclosureFetch.error.

# ponytail: community JSON mirror, can lag/go stale. fetched_at + source make
# staleness visible; feed URL is injected so we can swap to direct official
# (House Clerk ZIP/PDF, Senate eFD) fetching later without touching the screener.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone

log = logging.getLogger(__name__)

_USER_AGENT = "sapa-fund-research/1.0 (paper-trading; public-disclosure research)"

_BUY_WORDS = frozenset({"purchase", "buy", "p"})
_SELL_WORDS = frozenset({"sale", "sale_full", "sale_partial", "sell", "s"})

_AMOUNT_RE = re.compile(r"\$?([\d,]+)")


@dataclass(frozen=True)
class PoliticianTrade:
    ticker: str
    politician: str
    chamber: str            # "house" | "senate"
    transaction_type: str   # "buy" | "sell" | "exchange"
    owner: str
    amount_min: int
    amount_max: int
    transaction_date: date | None
    date_filed: date | None
    filing_lag_days: int | None
    source: str
    source_url: str


@dataclass(frozen=True)
class DisclosureFetch:
    trades: list[PoliticianTrade]
    fetched_at: str         # ISO-8601 UTC
    source: str
    error: str | None


def parse_amount_range(raw: str) -> tuple[int, int]:
    if not raw:
        return (0, 0)
    nums = [int(m.replace(",", "")) for m in _AMOUNT_RE.findall(raw)]
    if len(nums) >= 2:
        return (nums[0], nums[1])
    if len(nums) == 1:
        return (nums[0], nums[0])
    return (0, 0)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _classify(raw_type: str | None) -> str:
    t = (raw_type or "").strip().lower()
    if t in _BUY_WORDS or "purchase" in t:
        return "buy"
    if t in _SELL_WORDS or "sale" in t or "sell" in t:
        return "sell"
    return "exchange"


def _build_trade(*, ticker, politician, chamber, raw_type, owner,
                 amount, txn_date, filed_date, url) -> PoliticianTrade | None:
    ticker = (ticker or "").strip().upper()
    if not ticker or ticker in {"--", "N/A", "NA", ""}:
        return None
    amount_min, amount_max = parse_amount_range(amount or "")
    txn = _parse_date(txn_date)
    filed = _parse_date(filed_date)
    lag = (filed - txn).days if (txn and filed) else None
    return PoliticianTrade(
        ticker=ticker,
        politician=(politician or "unknown").strip(),
        chamber=chamber,
        transaction_type=_classify(raw_type),
        owner=(owner or "self").strip(),
        amount_min=amount_min,
        amount_max=amount_max,
        transaction_date=txn,
        date_filed=filed,
        filing_lag_days=lag,
        source=f"{chamber}_stock_watcher",
        source_url=(url or "").strip(),
    )


def _normalize_house_record(raw: dict) -> PoliticianTrade | None:
    return _build_trade(
        ticker=raw.get("ticker"),
        politician=raw.get("representative"),
        chamber="house",
        raw_type=raw.get("type"),
        owner=raw.get("owner"),
        amount=raw.get("amount"),
        txn_date=raw.get("transaction_date"),
        filed_date=raw.get("disclosure_date"),
        url=raw.get("ptr_link"),
    )


def _normalize_senate_record(raw: dict) -> PoliticianTrade | None:
    return _build_trade(
        ticker=raw.get("ticker"),
        politician=raw.get("senator"),
        chamber="senate",
        raw_type=raw.get("type"),
        owner=raw.get("owner"),
        amount=raw.get("amount"),
        txn_date=raw.get("transaction_date"),
        filed_date=raw.get("disclosure_date"),
        url=raw.get("ptr_link"),
    )


def _fetch_json(url: str, *, timeout: float) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class PoliticianDisclosureProvider:
    def __init__(self, *, house_url: str, senate_url: str, timeout: float = 10.0) -> None:
        self._house_url = house_url
        self._senate_url = senate_url
        self._timeout = timeout

    def fetch(self) -> DisclosureFetch:
        trades: list[PoliticianTrade] = []
        errors: list[str] = []
        sources: list[str] = []

        for url, normalizer, label in (
            (self._house_url, _normalize_house_record, "house"),
            (self._senate_url, _normalize_senate_record, "senate"),
        ):
            if not url:
                continue
            try:
                rows = _fetch_json(url, timeout=self._timeout)
                for raw in rows:
                    t = normalizer(raw)
                    if t is not None:
                        trades.append(t)
                sources.append(label)
            except (urllib.error.URLError, ValueError, TimeoutError) as exc:
                msg = f"{label}: {exc}"
                print(f"  [PROVIDER] source=politician_{label} error={exc}")
                errors.append(msg)

        return DisclosureFetch(
            trades=trades,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source="+".join(sources) if sources else "none",
            error="; ".join(errors) if errors else None,
        )
