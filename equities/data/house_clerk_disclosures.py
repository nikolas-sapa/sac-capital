"""Politician STOCK Act disclosure signals — House PTR (Periodic Transaction Report) filings.

Official source: US House of Representatives Clerk's Office
https://disclosures-clerk.house.gov/

Fetches the annual financial disclosure index (ZIP file with XML) and then downloads/parses
individual PTR PDFs (Periodic Transaction Reports = stock trades). All fetches are independent;
partial results are valid. Never raises — all errors surface in DisclosureFetch.error.

Extracted text format (digital PDF via pypdf):
  SP Intel Corporation - Common Stock
  (INTC) [OP]
  P 05/29/202605/29/2026$1,000,001 -
  $5,000,000

Fields per transaction:
- Owner code: SP=spouse, JT=joint, DC=dependent, blank/none=self
- Ticker: extracted from parentheses (INTC), ignore asset-type codes [OP]/[ST]
- Type: P=buy, S=sell, E=exchange
- Two dates: transaction_date THEN filing_date (each MM/DD/YYYY)
- Amount range: min - max (may span newline)
"""
from __future__ import annotations

import io
import logging
import re
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from defusedxml.ElementTree import fromstring as safe_fromstring
from pypdf import PdfReader

from equities.data.politician_disclosures import (
    DisclosureFetch,
    PoliticianTrade,
    _build_trade,
    _parse_date,
)

log = logging.getLogger(__name__)

_USER_AGENT = "sapa-fund-research/1.0 (paper-trading; public-disclosure research)"

# House Clerk financial disclosure ZIP index
_HOUSE_CLERK_ZIP_TEMPLATE = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.ZIP"

# PTR PDF download (direct)
_PTR_PDF_TEMPLATE = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{docid}.pdf"


def _fetch_bytes(url: str, *, timeout: float) -> bytes:
    """Fetch raw bytes from URL. Raises on network/HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_member_xml(root, year: int) -> list[dict]:
    """Parse House Clerk XML financial disclosure index.

    Returns list of Member dicts with keys: docid, first, last, prefix, suffix,
    state_district, filing_type, filing_date, year.
    Filters to FilingType == "P" (Periodic Transaction Report).
    """
    members = []
    for member_elem in root.findall(".//Member"):
        filing_type = member_elem.findtext("FilingType", "").strip()
        if filing_type != "P":
            continue  # Only PTRs; skip amendments, annual filings, etc.

        docid = member_elem.findtext("DocID", "").strip()
        first = member_elem.findtext("First", "").strip()
        last = member_elem.findtext("Last", "").strip()
        prefix = member_elem.findtext("Prefix", "").strip()
        suffix = member_elem.findtext("Suffix", "").strip()
        state_district = member_elem.findtext("StateDst", "").strip()
        filing_date = member_elem.findtext("FilingDate", "").strip()

        if not docid or not last:
            continue

        members.append({
            "docid": docid,
            "first": first,
            "last": last,
            "prefix": prefix,
            "suffix": suffix,
            "state_district": state_district,
            "filing_type": filing_type,
            "filing_date": filing_date,
            "year": year,
        })

    return members


def _politician_name(member: dict) -> str:
    """Format politician name from XML member dict."""
    parts = []
    if member.get("prefix"):
        parts.append(member["prefix"])
    if member.get("first"):
        parts.append(member["first"])
    if member.get("last"):
        parts.append(member["last"])
    if member.get("suffix"):
        parts.append(member["suffix"])
    return " ".join(p for p in parts if p) or "unknown"


def _filter_by_lookback(members: list[dict], lookback_days: int) -> list[dict]:
    """Filter members by filing date, keeping only those within lookback_days."""
    if lookback_days <= 0:
        return members

    today = date.today()
    cutoff = datetime(
        today.year,
        today.month,
        today.day,
        tzinfo=timezone.utc
    )
    cutoff_timestamp = cutoff.timestamp()

    filtered = []
    for member in members:
        filing_date_str = member.get("filing_date", "").strip()
        if not filing_date_str:
            continue
        try:
            filed = _parse_date(filing_date_str)
            if filed:
                filed_ts = datetime.combine(filed, datetime.min.time(), tzinfo=timezone.utc).timestamp()
                age_days = (cutoff_timestamp - filed_ts) / 86400.0
                if 0 <= age_days <= lookback_days:
                    filtered.append(member)
        except (ValueError, TypeError):
            continue

    return filtered


def parse_ptr_text(
    text: str,
    *,
    filed_date: date | str,
    politician: str,
    office: str,
    source_url: str,
) -> list[PoliticianTrade]:
    """Parse transaction rows from PTR PDF text.

    Extracts ticker, owner, type (buy/sell), dates, and amount ranges.
    Yields one PoliticianTrade per valid transaction row.
    Skips rows with no valid ticker or unparseable amounts.
    """
    trades: list[PoliticianTrade] = []

    # Normalize filed_date to date object
    if isinstance(filed_date, str):
        filed_date = _parse_date(filed_date)
    if not filed_date:
        return trades

    # Split text into lines for processing
    lines = text.split("\n")

    # Map owner code to string
    owner_map = {"SP": "spouse", "JT": "joint", "DC": "dependent_child", "D": "dependent_child"}

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines and headers
        if not line or line.startswith("Page ") or line.startswith("CONFIDENTIAL"):
            i += 1
            continue

        # Try to match owner code at start of line
        # Format: [OWNER_CODE] ASSET_NAME
        # Owner codes: SP (spouse), JT (joint), DC (dependent child)
        # If no owner code, it defaults to self
        owner_code_match = re.match(r"^(SP|JT|DC|D)?\s*(.+)$", line)
        if not owner_code_match or not owner_code_match.group(2):
            i += 1
            continue

        owner_code = owner_code_match.group(1)

        # Next line should contain ticker in parentheses
        i += 1
        if i >= len(lines):
            break

        ticker_line = lines[i].strip()
        ticker_match = re.search(r"\(([A-Z0-9]{1,5})\)", ticker_line)

        if not ticker_match:
            continue  # No valid ticker found, continue loop

        ticker = ticker_match.group(1)

        # Map owner code or default to self
        owner = owner_map.get(owner_code, "self")

        # Next line should have transaction type (P, S, E, etc.) and dates
        i += 1
        if i >= len(lines):
            break

        type_date_line = lines[i].strip()

        # Parse transaction type: P (purchase), S (sale), E (exchange)
        type_match = re.match(r"([PSE](?:\s*\([^)]*\))?)", type_date_line)
        if not type_match:
            continue  # No valid type, continue loop

        raw_type = type_match.group(1).strip()

        # Extract dates: two MM/DD/YYYY patterns (concatenated without space or with space)
        # Example: "05/29/202605/29/2026" or "05/29/2026 05/29/2026"
        date_pattern = r"(\d{2}/\d{2}/\d{4})\s*(\d{2}/\d{2}/\d{4})"
        date_match = re.search(date_pattern, type_date_line)

        if not date_match:
            continue  # No valid dates, continue loop

        txn_date_str = date_match.group(1)

        # Collect amount text (may span multiple lines)
        amount_text = type_date_line  # Start with current line in case amount starts here

        # Look ahead for amount on next lines
        j = i + 1
        while j < len(lines) and j < i + 3:  # Look ahead max 2 more lines
            next_line = lines[j].strip()
            if next_line:
                amount_text += " " + next_line
            j += 1

        # Parse amount range: $min - $max
        amount_match = re.search(r"\$?([\d,]+)\s*-\s*\$?([\d,]+)", amount_text)
        if not amount_match:
            i = j  # Move past the lines we checked
            continue

        try:
            amount_min = int(amount_match.group(1).replace(",", ""))
            amount_max = int(amount_match.group(2).replace(",", ""))
        except (ValueError, AttributeError):
            i = j  # Move past the lines we checked
            continue

        # Move pointer past amount lines
        i = j

        # Build the trade
        trade = _build_trade(
            ticker=ticker,
            politician=politician,
            chamber="house",
            raw_type=raw_type,
            owner=owner,
            amount=f"${amount_min:,} - ${amount_max:,}",
            txn_date=txn_date_str,
            filed_date=filed_date,
            url=source_url,
        )

        if trade is not None:
            trades.append(trade)

    return trades


class HouseClerkDisclosureProvider:
    """Fetch PTR (Periodic Transaction Report) stock trades from House Clerk.

    Queries the official House Clerk financial disclosure index (ZIP), filters
    to recent PTRs, downloads PDFs, and parses transaction rows via pypdf.
    """

    def __init__(
        self,
        *,
        year: int | None = None,
        lookback_days: int = 45,
        cache_dir: str = "data/house_ptr_cache",
        timeout: float = 30.0,
        max_pdfs: int = 80,
        rate_limit_s: float = 0.4,
    ) -> None:
        """Initialize provider.

        Args:
            year: Fiscal year to fetch (default: current UTC year).
            lookback_days: Only include PTRs filed within this many days.
            cache_dir: Directory to cache downloaded PDFs.
            timeout: HTTP request timeout in seconds.
            max_pdfs: Maximum number of PTR PDFs to fetch and parse.
            rate_limit_s: Sleep between PDF fetches (polite rate limiting).
        """
        if year is None:
            year = datetime.now(timezone.utc).year

        self._year = year
        self._lookback_days = lookback_days
        self._cache_dir = Path(cache_dir)
        self._timeout = timeout
        self._max_pdfs = max_pdfs
        self._rate_limit_s = rate_limit_s

        # Create cache directory if needed
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self) -> DisclosureFetch:
        """Fetch and parse PTRs. Never raises — errors surface in .error."""
        trades: list[PoliticianTrade] = []
        errors: list[str] = []

        fetched_at = datetime.now(timezone.utc).isoformat()

        # Step 1: Fetch and parse the ZIP index
        try:
            members = self._fetch_index()
        except Exception as exc:
            msg = f"Failed to fetch/parse House Clerk index: {exc}"
            log.warning(msg)
            return DisclosureFetch(
                trades=[],
                fetched_at=fetched_at,
                source="house_clerk",
                error=msg,
            )

        # Step 2: Filter by lookback and recent filings
        members = _filter_by_lookback(members, self._lookback_days)

        if not members:
            log.info(f"No PTRs found within {self._lookback_days} days")
            return DisclosureFetch(
                trades=[],
                fetched_at=fetched_at,
                source="house_clerk",
                error=None,
            )

        # Sort by filing date (newest first)
        members.sort(key=lambda m: m.get("filing_date", ""), reverse=True)

        # Cap at max_pdfs
        members = members[:self._max_pdfs]

        # Step 3: Fetch and parse PDFs
        for idx, member in enumerate(members):
            try:
                # Build source URL
                source_url = _PTR_PDF_TEMPLATE.format(year=self._year, docid=member["docid"])

                # Fetch or load from cache
                pdf_bytes = self._fetch_pdf(member["docid"])

                # Extract text
                try:
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    text = "".join(page.extract_text() or "" for page in reader.pages)
                except Exception as exc:
                    msg = f"Failed to extract PDF text ({member['docid']}): {exc}"
                    log.warning(msg)
                    errors.append(msg)
                    continue

                # Parse transactions
                politician_name = _politician_name(member)
                office = member.get("state_district", "unknown")
                filed_date_str = member.get("filing_date", "")

                trades_from_pdf = parse_ptr_text(
                    text,
                    filed_date=filed_date_str,
                    politician=politician_name,
                    office=office,
                    source_url=source_url,
                )

                trades.extend(trades_from_pdf)
                log.debug(f"Parsed {len(trades_from_pdf)} trades from {politician_name} ({member['docid']})")

                # Rate limiting between fetches (but not for cached PDFs)
                if idx < len(members) - 1:
                    time.sleep(self._rate_limit_s)

            except Exception as exc:
                msg = f"Failed to process PTR {member.get('docid', '?')}: {exc}"
                log.warning(msg)
                errors.append(msg)
                continue

        error_str = "; ".join(errors) if errors else None

        return DisclosureFetch(
            trades=trades,
            fetched_at=fetched_at,
            source="house_clerk",
            error=error_str,
        )

    def _fetch_index(self) -> list[dict]:
        """Fetch and parse House Clerk financial disclosure index ZIP.

        Returns list of Member dicts (from _parse_member_xml).
        Raises on network or parse error.
        """
        zip_url = _HOUSE_CLERK_ZIP_TEMPLATE.format(year=self._year)

        zip_bytes = _fetch_bytes(zip_url, timeout=self._timeout)

        # Extract XML from ZIP
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            xml_filename = f"{self._year}FD.xml"
            xml_bytes = z.read(xml_filename)

        root = safe_fromstring(xml_bytes)
        members = _parse_member_xml(root, self._year)

        return members

    def _fetch_pdf(self, docid: str) -> bytes:
        """Fetch PTR PDF. Uses cache if available, otherwise downloads.

        Returns PDF bytes.
        Raises on network or file error.
        """
        cache_path = self._cache_dir / f"{docid}.pdf"

        # Check cache first
        if cache_path.exists():
            log.debug(f"Loading cached PDF: {docid}")
            return cache_path.read_bytes()

        # Download
        pdf_url = _PTR_PDF_TEMPLATE.format(year=self._year, docid=docid)
        pdf_bytes = _fetch_bytes(pdf_url, timeout=self._timeout)

        # Cache it
        cache_path.write_bytes(pdf_bytes)
        log.debug(f"Cached PDF: {docid}")

        return pdf_bytes
