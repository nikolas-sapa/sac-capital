"""Executive branch financial disclosure signals — OGE Form 278-T (Periodic Transaction Reports).

Official source: U.S. Office of Government Ethics
https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index

Fetches periodic transaction reports (278-T) filed by executive officials and parses
transaction rows via pypdf. All fetches are independent; partial results are valid.
Never raises — all errors surface in DisclosureFetch.error.

**Enumeration note:** OGE Domino index is not machine-fetchable (JavaScript-rendered).
Falls back to a hardcoded registry of known high-signal filers (President, cabinet).
The registry can be updated with new PDF URLs as filings are discovered.

**OCR note:** Executive 278-T PDFs are OCR'd and may contain garbled text (spaces in
amounts, type codes). Parser uses fuzzy matching on asset names and type codes; rows
without a recognized ticker or type are skipped. Lossy but robust.

Extracted transaction format (from Trump 278-T sample):
  NVIDIA CORP lourchaae 2/10/2028 Yos $1,000,001 - $5 000,000
  BROADCOM INC COM lourchaao 2/10/2028 Vos $1 000 001 - $5,000,000
  MICROSOFT CORP ourchaae 3/1912026 Yoa $1,000 001-$5,000 000

Fields per transaction:
- Asset name (company name, no ticker in parens like House PTRs)
- Transaction type: purchase, sale (OCR-mangled: "lourchaae", "DUrchOSO", "ourchaao", etc.)
- Date: MM/DD/YYYY or OCR-mangled (missing slash, wrong year digit)
- Amount range: min - max (may contain spaces: $5 000 000, or bullet: •)
"""
from __future__ import annotations

import io
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from equities.data.politician_disclosures import (
    DisclosureFetch,
    PoliticianTrade,
    _build_trade,
    _parse_date,
)

log = logging.getLogger(__name__)

_USER_AGENT = "sapa-fund-research/1.0 (paper-trading; public-disclosure research)"

# Hardcoded registry of known executive 278-T filings.
# Format: (filer_name, filing_date_str, pdf_url)
# This is maintained as new filings are discovered on the OGE Domino index.
_EXECUTIVE_FILINGS = [
    (
        "Donald J. Trump",
        "2026-05-13",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/405E4EC4E27BE8D185258DF7002DD1C0/$FILE/Trump,%20Donald%20J.-05.08.2026-278T(2).pdf",
    ),
    (
        "Howard Lutnick",
        "2025-11-05",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/8C12E5475578E84385258D5C00345940/$FILE/Howard-Lutnick-11.05.2025-278T.pdf",
    ),
]

# Asset name → ticker mapping for OCR'd executive filings.
# Many exec PDFs don't have parenthetical tickers; fuzzy match on company name instead.
_ASSET_NAME_TO_TICKER = {
    "VANGUARD S&P 500 ETF": "VOO",
    "ISHARES CORE S&P 500 ETF": "IVV",
    "SERVICENOW INC": "NOW",
    "NVIDIA CORP": "NVDA",
    "ADOBE INC": "ADBE",
    "WORKDAY INC": "WDAY",
    "ORACLE CORPORATION": "ORCL",
    "MICROSOFT CORP": "MSFT",
    "BROADCOM INC": "AVGO",
    "SYNOPSYS INC": "SNPS",
    "CDW CORP": "CDW",
    "PROCTER & GAMBLE": "PG",
    "CADENCE DESIGN SYS": "CDNS",
    "TRANE TECHNOLOGIES": "TT",
    "TEXAS INSTRUMENTS": "TXN",
    "FIDELITY NATL INFORMATION": "FIS",
    "MOTOROLA SOLUTIONS": "MSI",
    "EATON CORP": "ETN",
    "STATE STREET INDSTL": "SSO",
    "INTEL CORPORATION": "INTC",
    "APPLE INC": "AAPL",
    "AMAZON.COM": "AMZN",
    "ALPHABET INC": "GOOGL",
    "TESLA INC": "TSLA",
    "META PLATFORMS": "META",
    "NVIDIA": "NVDA",
    "MICROSOFT": "MSFT",
    "APPLE": "AAPL",
    "AMAZON": "AMZN",
    "GOOGLE": "GOOGL",
}


def _fetch_bytes(url: str, *, timeout: float) -> bytes:
    """Fetch raw bytes from URL. Raises on network/HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _normalize_amount_text(raw: str) -> str:
    """Normalize OCR'd amount text: remove intra-number spaces, convert bullets to dashes.

    Examples:
        "$5 000 000" -> "$5000000"
        "$1,000,001 • $5 000,000" -> "$1,000,001 - $5000000"
    """
    # Remove spaces within numbers (but preserve spaces around $ and --)
    # Collapse any run of spaces between digits: 5 000 000 -> 5000000
    normalized = re.sub(r'(\d)\s+(\d)', r'\1\2', raw)
    # Convert bullet separators to dashes
    normalized = normalized.replace('•', '-')
    return normalized


def _normalize_type_text(raw: str) -> str:
    """Normalize OCR'd transaction type. Handles mangled purchase/sale codes.

    Examples:
        "lourchaae" -> "P"
        "DUrchOSO" -> "P"
        "ourchaao" -> "P"
        "sol" -> "S"
        "P" -> "P"
    """
    t = (raw or "").strip().upper()
    if not t:
        return t

    # Fuzzy: if contains "PURCH", "URCH", "OURCHA" (OCR variants of purchase)
    if re.search(r'PURCH|URCH|OURCHA', t):
        return "P"
    # Fuzzy: if "SAL" or "SOL" appears, classify as sale
    if re.search(r'SAL|SOL', t):
        return "S"
    # Passthrough short codes
    return t


def _repair_ocr_date(raw_date: str) -> str | None:
    """Repair common OCR errors in dates.

    Handles:
        "3/1912026" -> "3/19/2026" (missing slash)
        "3/212026" -> "3/21/2026" (missing slash)
        "2/1012026" -> "2/10/2026" (missing slash)

    Returns the repaired date string, or None if it can't be fixed.
    """
    if not raw_date:
        return None

    # If it already parses correctly, return as-is
    if _parse_date(raw_date) is not None:
        return raw_date

    # Try to fix common patterns: M/DDYYYY or MM/DDYYYY (missing second slash)
    # Pattern: digit(s), slash, then 6-8 digits (day + year combined)
    match = re.match(r'^(\d{1,2})/(\d{2,4})(\d{4})$', raw_date)
    if match:
        month = match.group(1)
        day_part = match.group(2)
        year = match.group(3)

        # If day_part is 3-4 digits, it might be "19" + "2" (corrupted year start) or "2" + "12" (extra digit)
        # Try to extract 2-digit day: take last 2 digits if 3-4 digits, else as-is
        if len(day_part) == 3:
            # "191" -> try "19", or try "191"[:2] = "19"
            day = day_part[:2]
        elif len(day_part) == 4:
            # "2120" -> try "21"
            day = day_part[:2]
        else:
            # 2 digits
            day = day_part

        repaired = f"{month}/{day}/{year}"
        if _parse_date(repaired) is not None:
            return repaired

    return None


def _resolve_ticker(asset_name: str) -> str | None:
    """Resolve asset name to ticker via the hardcoded map.

    Tries exact match first, then case-insensitive prefix match.
    Returns None if no match found.
    """
    if not asset_name:
        return None

    asset_clean = asset_name.strip().upper()

    # Exact match (case-insensitive)
    for name_key, ticker in _ASSET_NAME_TO_TICKER.items():
        if asset_clean == name_key.upper():
            return ticker

    # Prefix match: check if any map key starts with the asset name
    for name_key, ticker in _ASSET_NAME_TO_TICKER.items():
        if name_key.upper().startswith(asset_clean):
            return ticker

    return None


def parse_278t_text(
    text: str,
    *,
    filer: str,
    filed_date: date | str,
    source_url: str,
) -> list[PoliticianTrade]:
    """Parse transaction rows from 278-T PDF text.

    Extracts asset name (resolves to ticker), type (buy/sell), dates, and amounts.
    Skips rows with:
    - No resolvable ticker (asset name not in name_to_ticker map)
    - Unparseable amount ranges
    - Missing or invalid transaction dates

    Yields one PoliticianTrade per valid transaction row.

    Args:
        text: Extracted text from 278-T PDF (via pypdf).
        filer: Filer's name (e.g., "Donald J. Trump").
        filed_date: Date the 278-T was filed (date object or MM/DD/YYYY string).
        source_url: URL of the PDF for attribution.

    Returns:
        List of PoliticianTrade objects.
    """
    trades: list[PoliticianTrade] = []

    # Normalize filed_date to date object
    if isinstance(filed_date, str):
        filed_date = _parse_date(filed_date)
    if not filed_date:
        return trades

    lines = text.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        # Skip empty lines, headers, and noise
        if not line or line.startswith("Page ") or "Confidential" in line or line.startswith("OGE Form"):
            continue

        # Look for asset names: check if any known asset keyword is in this line
        matched_ticker = None

        for asset_key in _ASSET_NAME_TO_TICKER:
            # Look for the asset key anywhere in the line (case-insensitive)
            if asset_key.upper() in line.upper():
                matched_ticker = _ASSET_NAME_TO_TICKER[asset_key]
                break

        if not matched_ticker:
            continue  # No recognized asset in this line

        # Collect text from this line and potentially next lines for multi-line rows
        # (multi-line rows are rare; most are single-line with all data)
        collected = line

        j = i
        max_lookahead = 1  # Be conservative: only look at next line if it's clearly a continuation
        while j < len(lines) and j < i + max_lookahead:
            next_line = lines[j].strip()
            # Only continue if it starts with $ (amount continuation) or is clearly not a new transaction
            # A new transaction starts with "N ASSETNAME" (digit-space-capital), so skip those
            if next_line and next_line.startswith("$"):
                collected += " " + next_line
                j += 1
            elif next_line and next_line[0].isdigit() and len(next_line) > 1 and next_line[1] == " ":
                # This looks like "N ASSETNAME" (new transaction), stop here
                break
            elif next_line and next_line[0].isalpha():
                # All-alphabetic line, might be continuation (header/label), but conservative approach: skip
                break
            else:
                # Ambiguous; skip it
                break

        i = j

        # Extract type: look for purchase/sale keywords
        type_match = re.search(r'[Pp]urch|[Oo]urch|[Ss]al|[Ss]ol|[Uu]rch|^[PSE]', collected)
        if not type_match:
            continue

        raw_type_text = collected[type_match.start():type_match.end()]
        raw_type = _normalize_type_text(raw_type_text)

        # Extract date: MM/DD/YYYY or OCR-mangled (missing slashes, garbled digits)
        # Patterns: MM/DD/YYYY, M/DD/YYYY, MM/DDYYYY, MMDDYYYY, etc.
        date_patterns = [
            r'(\d{1,2}/\d{1,2}/\d{4})',        # MM/DD/YYYY
            r'(\d{1,2}/\d{2,3}/\d{4})',        # M/DD/YYYY (space for second slash)
            r'(\d{1,2}/\d{4,8})',              # M/DDYYYY or M/YYYY (missing or bad slash)
        ]

        txn_date_str = None
        for pattern in date_patterns:
            date_match = re.search(pattern, collected)
            if date_match:
                raw_date = date_match.group(1)
                # Try to parse it directly first
                if _parse_date(raw_date) is not None:
                    txn_date_str = raw_date
                    break
                # Try to repair OCR errors
                repaired = _repair_ocr_date(raw_date)
                if repaired is not None:
                    txn_date_str = repaired
                    break

        if not txn_date_str:
            continue  # No valid date found

        # Extract amount range: $min - $max (with possible OCR noise like spaces/commas/dots)
        # Strategy: find dollar signs and extract numbers after them on both sides of a dash
        amount_text_normalized = _normalize_amount_text(collected)

        # Find all sequences like $DIGITS,DIGITS followed by - $DIGITS,DIGITS
        # More permissive: allow commas, spaces, and dots between digits
        amount_pattern = r'\$\s*([\d,.\s ]+?)\s*[-•]\s*\$\s*([\d,.\s ]+)'
        amount_match = re.search(amount_pattern, amount_text_normalized)

        if not amount_match:
            continue

        try:
            # Clean up amount strings: remove all spaces, commas, and dots, then convert
            amount_min_str = re.sub(r'[,.\s]', '', amount_match.group(1))
            amount_max_str = re.sub(r'[,.\s]', '', amount_match.group(2))
            amount_min = int(amount_min_str)
            amount_max = int(amount_max_str)
        except (ValueError, IndexError):
            continue

        # Build the trade
        trade = _build_trade(
            ticker=matched_ticker,
            politician=filer,
            chamber="executive",
            raw_type=raw_type,
            owner="self",  # Executive filings don't typically break out owner codes
            amount=f"${amount_min:,} - ${amount_max:,}",
            txn_date=txn_date_str,
            filed_date=filed_date,
            url=source_url,
        )

        if trade is not None:
            trades.append(trade)

    return trades


class OGEExecutiveProvider:
    """Fetch periodic transaction reports (278-T) from executive branch officials.

    Uses a hardcoded registry of known filers (President, cabinet members).
    Caches PDFs locally. Parses OCR'd transaction rows via pypdf.
    Never raises; errors surface in DisclosureFetch.error.
    """

    def __init__(
        self,
        *,
        lookback_days: int = 120,
        max_pdfs: int = 40,
        cache_dir: str = "data/oge_cache",
        timeout: float = 40.0,
        rate_limit_s: float = 0.5,
        filers: list[tuple[str, str, str]] | None = None,
    ) -> None:
        """Initialize provider.

        Args:
            lookback_days: Only include 278-Ts filed within this many days.
            max_pdfs: Maximum number of PDFs to fetch and parse.
            cache_dir: Directory to cache downloaded PDFs.
            timeout: HTTP request timeout in seconds.
            rate_limit_s: Sleep between PDF fetches (polite rate limiting).
            filers: Override the default hardcoded registry. List of (name, date, url) tuples.
        """
        self._lookback_days = lookback_days
        self._max_pdfs = max_pdfs
        self._cache_dir = Path(cache_dir)
        self._timeout = timeout
        self._rate_limit_s = rate_limit_s
        self._filers = filers if filers is not None else _EXECUTIVE_FILINGS

        # Create cache directory
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self) -> DisclosureFetch:
        """Fetch and parse 278-T filings. Never raises — errors surface in .error."""
        trades: list[PoliticianTrade] = []
        errors: list[str] = []

        fetched_at = datetime.now(timezone.utc).isoformat()

        # Filter filers by lookback_days
        today = date.today()
        cutoff = datetime(
            today.year, today.month, today.day, tzinfo=timezone.utc
        ).timestamp()

        filtered_filers = []
        for filer_name, filing_date_str, pdf_url in self._filers:
            if self._lookback_days <= 0:
                filtered_filers.append((filer_name, filing_date_str, pdf_url))
                continue

            # Parse the filing date
            try:
                filed = _parse_date(filing_date_str)
                if not filed:
                    continue
                filed_ts = datetime.combine(
                    filed, datetime.min.time(), tzinfo=timezone.utc
                ).timestamp()
                age_days = (cutoff - filed_ts) / 86400.0
                if 0 <= age_days <= self._lookback_days:
                    filtered_filers.append((filer_name, filing_date_str, pdf_url))
            except (ValueError, TypeError):
                continue

        if not filtered_filers:
            log.info(f"No executive filings within {self._lookback_days} days")
            return DisclosureFetch(
                trades=[],
                fetched_at=fetched_at,
                source="oge_executive",
                error=None,
            )

        # Cap at max_pdfs
        filtered_filers = filtered_filers[:self._max_pdfs]

        # Fetch and parse PDFs
        for idx, (filer_name, filing_date_str, pdf_url) in enumerate(filtered_filers):
            try:
                # Fetch or load from cache
                pdf_bytes = self._fetch_pdf(pdf_url)

                # Extract text
                try:
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    text = "".join(page.extract_text() or "" for page in reader.pages)
                except Exception as exc:
                    msg = f"Failed to extract PDF text ({filer_name}): {exc}"
                    log.warning(msg)
                    errors.append(msg)
                    continue

                # Parse transactions
                trades_from_pdf = parse_278t_text(
                    text,
                    filer=filer_name,
                    filed_date=filing_date_str,
                    source_url=pdf_url,
                )

                trades.extend(trades_from_pdf)
                log.debug(
                    f"Parsed {len(trades_from_pdf)} trades from {filer_name}"
                )

                # Rate limiting between fetches
                if idx < len(filtered_filers) - 1:
                    time.sleep(self._rate_limit_s)

            except Exception as exc:
                msg = f"Failed to process 278-T for {filer_name}: {exc}"
                log.warning(msg)
                errors.append(msg)
                continue

        error_str = "; ".join(errors) if errors else None

        return DisclosureFetch(
            trades=trades,
            fetched_at=fetched_at,
            source="oge_executive",
            error=error_str,
        )

    def _fetch_pdf(self, pdf_url: str) -> bytes:
        """Fetch or load cached PDF.

        Returns PDF bytes. Raises on network or file error.
        """
        # Use URL hash as cache key
        cache_key = str(hash(pdf_url) & 0xffffffff)
        cache_path = self._cache_dir / f"{cache_key}.pdf"

        if cache_path.exists():
            log.debug(f"Loading cached PDF: {cache_key}")
            return cache_path.read_bytes()

        # Download
        pdf_bytes = _fetch_bytes(pdf_url, timeout=self._timeout)

        # Cache it
        cache_path.write_bytes(pdf_bytes)
        log.debug(f"Cached PDF: {cache_key}")

        return pdf_bytes
