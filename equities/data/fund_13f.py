"""SEC 13F-HR smart-money context provider — track hedge fund US-equity holdings.

Official source: SEC EDGAR Data API
https://data.sec.gov/submissions/CIK{cik}.json

Fetches quarterly 13F-HR filings, parses XML info tables, and diffs quarter-over-quarter
to infer position changes (new/increased/reduced/exited). All fetches are independent;
partial results are valid. Never raises — all errors surface in Fund13FSnapshot.error.

13F-HR filing structure:
- CIK={cik} → Submissions API JSON
- Filter to form = "13F-HR" (quarterly holdings report)
- For each filing: accessionNumber + primaryDocument → filing directory
- Download {accession_nodashes}/index.json → list files
- Parse {filename}.xml where name doesn't contain "primary" (e.g., salp13fq1xml.xml)
- XML elements ending in "infoTable" contain holdings
  - nameOfIssuer, cusip, value (thousands USD), shrsOrPrnAmt/sshPrnamt (shares)
  - putCall: "Put"/"Call"/absent(=long stock)

Position types: "long" (equity), "put", "call"
Value: in USD (value_from_sec * 1000)
Shares: integer count or None if missing
"""
from __future__ import annotations

import io
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import fromstring as etree_fromstring
from typing import Any

log = logging.getLogger(__name__)

_USER_AGENT = "sapa-fund-research nikolas.sapalidis@gmail.com"

# SEC Submissions API
_SUBMISSIONS_API_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# Filing directory index
_FILING_INDEX_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodashes}/index.json"


def _fetch_bytes(url: str, *, timeout: float) -> bytes:
    """Fetch raw bytes from URL. Raises on network/HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _fetch_json(url: str, *, timeout: float) -> dict[str, Any]:
    """Fetch and parse JSON from URL. Raises on network/HTTP/parse error."""
    data = _fetch_bytes(url, timeout=timeout)
    return json.loads(data.decode("utf-8"))


@dataclass(frozen=True)
class Holding:
    """Single position from a 13F info table."""
    issuer: str
    cusip: str
    position_type: str  # "long", "put", "call"
    value_usd: int  # dollars (value_from_sec * 1000)
    shares: int | None  # share count or None if missing


@dataclass(frozen=True)
class PositionChange:
    """Diff between quarters for (issuer, position_type) pair."""
    issuer: str
    position_type: str
    change: str  # "new", "increased", "reduced", "exited", "unchanged"
    prev_value_usd: int
    curr_value_usd: int


@dataclass(frozen=True)
class Fund13FSnapshot:
    """Complete 13F snapshot: holdings, changes, totals."""
    cik: str
    fund_name: str
    period_filed: str  # latest filing date (YYYY-MM-DD format)
    holdings: list[Holding] = field(default_factory=list)
    changes: list[PositionChange] = field(default_factory=list)
    total_long_usd: int = 0
    total_put_usd: int = 0
    total_call_usd: int = 0
    source_url: str = ""
    fetched_at: str = ""
    error: str | None = None


def parse_info_table_xml(xml_str: str) -> list[Holding]:
    """Parse 13F info table XML into aggregated holdings.

    Aggregates multiple rows for the same (issuer, position_type) by summing
    value_usd and shares. Returns list of unique Holding objects.
    """
    holdings: dict[tuple[str, str], dict[str, Any]] = {}

    try:
        root = etree_fromstring(xml_str)
    except Exception as exc:
        log.warning(f"Failed to parse 13F XML: {exc}")
        return []

    # Navigate to info table elements (handles namespaces via endswith)
    for elem in root.iter():
        if not elem.tag.endswith("infoTable"):
            continue

        # Extract issuer, cusip, position_type, value, shares
        issuer_text = None
        cusip_text = None
        put_call = None
        value_raw = 0
        shares_count = None

        for child in elem:
            tag = child.tag
            text = (child.text or "").strip()

            if tag.endswith("nameOfIssuer"):
                issuer_text = text
            elif tag.endswith("cusip"):
                cusip_text = text
            elif tag.endswith("value"):
                try:
                    value_raw = int(text)
                except (ValueError, TypeError):
                    pass
            elif tag.endswith("putCall"):
                put_call = text
            elif tag.endswith("shrsOrPrnAmt"):
                # Contains sshPrnamt child for share count
                for sub in child:
                    if sub.tag.endswith("sshPrnamt"):
                        try:
                            shares_count = int((sub.text or "").strip())
                        except (ValueError, TypeError):
                            pass

        # Validate required fields
        if not issuer_text or not cusip_text:
            continue

        # Determine position type
        position_type = "long"
        if put_call == "Put":
            position_type = "put"
        elif put_call == "Call":
            position_type = "call"

        # SEC Form 13F reports `value` in WHOLE DOLLARS since the 2023 rule change.
        # ponytail: pre-2023 filings used thousands; this fund only filed post-2023,
        # so no scaling. Revisit if backfilling funds with pre-2023 13Fs.
        value_usd = value_raw

        # Aggregate by (issuer, position_type)
        key = (issuer_text, position_type)
        if key in holdings:
            # Sum value
            holdings[key]["value_usd"] += value_usd
            # Sum shares (if both are None, keep None; if either is a number, sum)
            prev_shares = holdings[key]["shares"]
            if prev_shares is not None and shares_count is not None:
                holdings[key]["shares"] = prev_shares + shares_count
            elif shares_count is not None:
                holdings[key]["shares"] = shares_count
        else:
            holdings[key] = {
                "issuer": issuer_text,
                "cusip": cusip_text,
                "position_type": position_type,
                "value_usd": value_usd,
                "shares": shares_count,
            }

    return [
        Holding(
            issuer=h["issuer"],
            cusip=h["cusip"],
            position_type=h["position_type"],
            value_usd=h["value_usd"],
            shares=h["shares"],
        )
        for h in holdings.values()
    ]


def compute_changes(
    prev_holdings: list[Holding],
    curr_holdings: list[Holding],
) -> list[PositionChange]:
    """Diff two quarters' holdings to infer changes.

    Classifies each (issuer, position_type) as: new, increased, reduced, exited, unchanged.
    """
    # Build lookup maps
    prev_map = {(h.issuer, h.position_type): h for h in prev_holdings}
    curr_map = {(h.issuer, h.position_type): h for h in curr_holdings}

    # Union of keys from both quarters (to catch exits)
    all_keys = set(prev_map.keys()) | set(curr_map.keys())

    changes = []
    for key in all_keys:
        issuer, pos_type = key
        prev_holding = prev_map.get(key)
        curr_holding = curr_map.get(key)

        prev_value = prev_holding.value_usd if prev_holding else 0
        curr_value = curr_holding.value_usd if curr_holding else 0

        if prev_holding is None:
            # New position
            change_type = "new"
        elif curr_holding is None:
            # Exited position
            change_type = "exited"
        elif curr_value > prev_value:
            change_type = "increased"
        elif curr_value < prev_value:
            change_type = "reduced"
        else:
            change_type = "unchanged"

        changes.append(
            PositionChange(
                issuer=issuer,
                position_type=pos_type,
                change=change_type,
                prev_value_usd=prev_value,
                curr_value_usd=curr_value,
            )
        )

    return sorted(changes, key=lambda c: (c.change, -c.curr_value_usd, c.issuer))


class Fund13FProvider:
    """Fetch and parse 13F-HR filings for a hedge fund.

    Never raises. All errors are captured in Fund13FSnapshot.error.
    """

    def __init__(
        self,
        *,
        cik: str,
        fund_name: str = "",
        cache_dir: str = "data/fund_13f_cache",
        timeout: float = 30.0,
        rate_limit_s: float = 0.4,
    ) -> None:
        """Initialize provider.

        Args:
            cik: SEC CIK (e.g., "2045724" for Situational Awareness LP)
            fund_name: Human-readable fund name
            cache_dir: Directory to cache downloaded XML files
            timeout: HTTP request timeout in seconds
            rate_limit_s: Sleep between requests (polite rate limiting)
        """
        self._cik = cik
        self._fund_name = fund_name
        self._cache_dir = Path(cache_dir)
        self._timeout = timeout
        self._rate_limit_s = rate_limit_s

        # Create cache directory if needed
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def latest_two_infotables(self) -> tuple[list[Holding], list[Holding]]:
        """Fetch the two most recent 13F-HR info table XMLs.

        Returns (prev_holdings, curr_holdings). If fewer than 2 filings exist,
        pads with empty lists. Raises on network/parse error.
        """
        accessions = self._fetch_13f_accessions()
        if not accessions:
            return [], []

        # Take two most recent
        accessions = accessions[:2]

        holdings_list = []
        for idx, acc_number in enumerate(accessions):
            try:
                xml_str = self._fetch_info_table_xml(acc_number)
                holdings = parse_info_table_xml(xml_str)
                holdings_list.append(holdings)
                # Rate limit between fetches (but not for cached)
                if idx < len(accessions) - 1:
                    time.sleep(self._rate_limit_s)
            except Exception as exc:
                log.warning(f"Failed to fetch info table for {acc_number}: {exc}")
                holdings_list.append([])

        # Pad if only one or zero
        while len(holdings_list) < 2:
            holdings_list.append([])

        return holdings_list[1], holdings_list[0]  # [prev, curr]

    def snapshot(self) -> Fund13FSnapshot:
        """Build a complete 13F snapshot. Never raises — errors in .error field."""
        fetched_at = datetime.now(timezone.utc).isoformat()

        try:
            prev_holdings, curr_holdings = self.latest_two_infotables()
        except Exception as exc:
            msg = f"Failed to fetch 13F-HR filings: {exc}"
            log.warning(msg)
            return Fund13FSnapshot(
                cik=self._cik,
                fund_name=self._fund_name,
                period_filed="",
                holdings=[],
                changes=[],
                total_long_usd=0,
                total_put_usd=0,
                total_call_usd=0,
                source_url="",
                fetched_at=fetched_at,
                error=msg,
            )

        # Get the filing date of the latest filing
        period_filed = ""
        try:
            period_filed = self._fetch_latest_filing_date()
        except Exception:
            pass

        # Compute totals from current holdings
        total_long_usd = sum(h.value_usd for h in curr_holdings if h.position_type == "long")
        total_put_usd = sum(h.value_usd for h in curr_holdings if h.position_type == "put")
        total_call_usd = sum(h.value_usd for h in curr_holdings if h.position_type == "call")

        # Compute changes
        changes = compute_changes(prev_holdings, curr_holdings)

        # Build source URL
        source_url = _SUBMISSIONS_API_TEMPLATE.format(cik=int(self._cik))

        return Fund13FSnapshot(
            cik=self._cik,
            fund_name=self._fund_name,
            period_filed=period_filed,
            holdings=curr_holdings,
            changes=changes,
            total_long_usd=total_long_usd,
            total_put_usd=total_put_usd,
            total_call_usd=total_call_usd,
            source_url=source_url,
            fetched_at=fetched_at,
            error=None,
        )

    def context_summary(self) -> str:
        """Generate LLM-readable context paragraph for the analyst.

        Format: fund name, filing date, totals, and summary of position changes.
        """
        snap = self.snapshot()

        if snap.error:
            return f"Smart-money 13F ({self._fund_name}): Failed to fetch latest filing — {snap.error}"

        if not snap.holdings:
            return f"Smart-money 13F ({self._fund_name}): No holdings data available."

        # Summarize changes by type
        def summary_by_type(change_type: str) -> list[str]:
            return [
                c.issuer
                for c in snap.changes
                if c.change == change_type
            ][:5]  # Top 5 per category

        new_longs = [
            c.issuer for c in snap.changes
            if c.change == "new" and c.position_type == "long"
        ][:3]
        increased_longs = [
            c.issuer for c in snap.changes
            if c.change == "increased" and c.position_type == "long"
        ][:3]
        exited = [
            c.issuer for c in snap.changes
            if c.change == "exited"
        ][:3]
        puts = [
            h.issuer for h in snap.holdings
            if h.position_type == "put"
        ][:3]

        # Format summary
        parts = [
            f"Smart-money 13F — {self._fund_name} (filed {snap.period_filed}):",
            f"NET POSITIONING ${snap.total_long_usd / 1e9:.2f}B long / ${snap.total_put_usd / 1e9:.2f}B puts / ${snap.total_call_usd / 1e9:.2f}B calls.",
        ]

        if new_longs:
            parts.append(f"NEW longs: {', '.join(new_longs)}.")
        if increased_longs:
            parts.append(f"INCREASED: {', '.join(increased_longs)}.")
        if exited:
            parts.append(f"EXITED: {', '.join(exited)}.")
        if puts:
            parts.append(f"Largest put themes (bearish): {', '.join(puts)}.")

        return " ".join(parts)

    def _fetch_13f_accessions(self) -> list[str]:
        """Fetch CIK's submissions and extract 13F-HR accession numbers.

        Returns list sorted newest-first. Raises on network/parse error.
        """
        url = _SUBMISSIONS_API_TEMPLATE.format(cik=int(self._cik))
        data = _fetch_json(url, timeout=self._timeout)

        accessions = []
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])

        for form, acc_num in zip(forms, accession_numbers):
            if form.startswith("13F-HR"):
                accessions.append(acc_num)

        return accessions

    def _fetch_latest_filing_date(self) -> str:
        """Fetch the date of the latest 13F-HR filing. Returns YYYY-MM-DD or empty."""
        url = _SUBMISSIONS_API_TEMPLATE.format(cik=int(self._cik))
        data = _fetch_json(url, timeout=self._timeout)

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        filing_dates = filings.get("filingDate", [])

        for form, filing_date in zip(forms, filing_dates):
            if form.startswith("13F-HR"):
                return filing_date
        return ""

    def _fetch_info_table_xml(self, accession_number: str) -> str:
        """Fetch 13F info table XML for an accession number.

        Returns XML string. Uses cache if available, otherwise downloads.
        Raises on network or file error.
        """
        cache_path = self._cache_dir / f"{accession_number}.xml"

        # Check cache first
        if cache_path.exists():
            log.debug(f"Loading cached 13F XML: {accession_number}")
            return cache_path.read_text(encoding="utf-8")

        # Build filing directory URL
        accession_nodashes = accession_number.replace("-", "")
        index_url = _FILING_INDEX_TEMPLATE.format(
            cik=int(self._cik),
            accession_nodashes=accession_nodashes,
        )

        # Fetch index to find the info table XML filename
        try:
            index_data = _fetch_json(index_url, timeout=self._timeout)
        except Exception as exc:
            raise ValueError(f"Failed to fetch filing index for {accession_number}: {exc}")

        # Find the XML file that isn't the primary doc
        xml_filename = None
        for item in index_data.get("directory", {}).get("item", []):
            name = item.get("name", "")
            if name.endswith(".xml") and "primary" not in name.lower():
                xml_filename = name
                break

        if not xml_filename:
            raise ValueError(f"No 13F info table XML found for {accession_number}")

        # Download the XML
        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(self._cik)}/"
            f"{accession_nodashes}/{xml_filename}"
        )
        xml_bytes = _fetch_bytes(xml_url, timeout=self._timeout)
        xml_str = xml_bytes.decode("utf-8")

        # Cache it
        cache_path.write_text(xml_str, encoding="utf-8")
        log.debug(f"Cached 13F XML: {accession_number}")

        return xml_str
