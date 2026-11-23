"""Politician STOCK Act disclosure signals — shared types and helpers.

The live providers fetch direct official sources: House Clerk disclosures
(`house_clerk_disclosures.py`), Senate eFD (`senate_efd_disclosures.py`),
OGE executive filings (`oge_executive.py`, `executive_disclosures.py`),
fanned out by `composite_disclosures.py`. The S3 stock-watcher mirrors were
retired after the upstream feeds went 403.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

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


def parse_amount_range(raw: object) -> tuple[int, int]:
    if not raw:
        return (0, 0)
    nums = [int(m.replace(",", "")) for m in _AMOUNT_RE.findall(str(raw))]
    if len(nums) >= 2:
        return (nums[0], nums[1])
    if len(nums) == 1:
        return (nums[0], nums[0])
    return (0, 0)


def _parse_date(raw: object) -> date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
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
