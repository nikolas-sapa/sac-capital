"""Politician STOCK Act disclosure signals — Senate PTR (Periodic Transaction Report) filings.

Official source: Senate eFilings Disclosure (eFD)
https://efdsearch.senate.gov/search/home/

Flow:
1. GET home page, extract CSRF token and session cookie
2. POST agreement acceptance with CSRF token
3. POST AJAX search for recent PTRs (report_types=[11], date range)
4. For each recent PTR, fetch and parse HTML table of transactions

IMPORTANT: Senate PTRs rendered electronically use HTML tables. Older PDFs may not be supported.
Partial results are valid. Never raises — all errors surface in DisclosureFetch.error.
"""
from __future__ import annotations

import html.parser
import io
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.cookiejar import CookieJar
from pathlib import Path

from equities.data.politician_disclosures import (
    DisclosureFetch,
    PoliticianTrade,
    _build_trade,
    _parse_date,
)

log = logging.getLogger(__name__)

_USER_AGENT = "sapa-fund-research/1.0 (paper-trading; public-disclosure research)"

_SENATE_HOME_URL = "https://efdsearch.senate.gov/search/home/"
_SENATE_SEARCH_AJAX_URL = "https://efdsearch.senate.gov/search/report/data/"
_SENATE_PTR_DETAIL_TEMPLATE = "https://efdsearch.senate.gov/search/view/ptr/{uuid}/"


class _HTMLTransactionTableParser(html.parser.HTMLParser):
    """Parse transaction table rows from Senate eFD PTR HTML.

    Expects structure like:
      <table>
        <tr>
          <td>TICKER</td><td>TYPE</td><td>AMOUNT_MIN - AMOUNT_MAX</td>
          <td>TXN_DATE</td><td>FILED_DATE</td>
        </tr>
      </table>
    """

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.in_table = False
        self.in_td = False
        self.current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.current_row = []
        elif tag == "td" and self.in_table:
            self.in_td = True
            self.current_text = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "td" and self.in_table:
            self.in_td = False
            self.current_row.append(self.current_text.strip())
        elif tag == "tr" and self.in_table and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = []

    def handle_data(self, data):
        if self.in_td:
            self.current_text += data


def parse_senate_ptr_html(
    html: str,
    *,
    date_filed: date | str,
    politician: str,
    office: str,
    source_url: str,
) -> list[PoliticianTrade]:
    """Parse transaction rows from Senate eFD PTR HTML table.

    Extracts ticker, type (buy/sell), amount ranges, and dates.
    Yields one PoliticianTrade per valid transaction row.
    Skips rows with no valid ticker or unparseable amounts.

    HTML table columns: ticker, type, amount_range, txn_date, filed_date
    """
    trades: list[PoliticianTrade] = []

    # Normalize filed_date to date object
    if isinstance(date_filed, str):
        date_filed = _parse_date(date_filed)
    if not date_filed:
        return trades

    # Parse the HTML table
    parser = _HTMLTransactionTableParser()
    try:
        parser.feed(html)
    except Exception as exc:
        log.warning(f"Failed to parse Senate PTR HTML: {exc}")
        return trades

    # Process rows (skip header row if present)
    for row in parser.rows:
        if len(row) < 5:
            continue  # Skip malformed rows

        ticker_raw = row[0].strip().upper()
        type_raw = row[1].strip().upper()
        amount_raw = row[2].strip()
        txn_date_raw = row[3].strip()

        # Skip if ticker is empty or N/A
        if not ticker_raw or ticker_raw in {"--", "N/A", "NA", ""}:
            continue

        # Parse amount range: expect format like "$1,000,000 - $5,000,000"
        amount_match = re.search(r"\$?([\d,]+)\s*-\s*\$?([\d,]+)", amount_raw)
        if not amount_match:
            continue

        try:
            amount_min = int(amount_match.group(1).replace(",", ""))
            amount_max = int(amount_match.group(2).replace(",", ""))
        except (ValueError, AttributeError):
            continue

        # Build the trade
        trade = _build_trade(
            ticker=ticker_raw,
            politician=politician,
            chamber="senate",
            raw_type=type_raw,
            owner="self",  # Senate HTML tables don't typically show owner code
            amount=f"${amount_min:,} - ${amount_max:,}",
            txn_date=txn_date_raw,
            filed_date=date_filed,
            url=source_url,
        )

        if trade is not None:
            trades.append(trade)

    return trades


class SenateEFDDisclosureProvider:
    """Fetch PTR (Periodic Transaction Report) stock trades from Senate eFilings Disclosure.

    Queries the Senate eFD search API for recent PTRs, accepts agreement gate,
    and parses transaction HTML tables.
    """

    def __init__(
        self,
        *,
        lookback_days: int = 45,
        max_reports: int = 80,
        cache_dir: str = "data/senate_efd_cache",
        timeout: float = 30.0,
        rate_limit_s: float = 0.4,
    ) -> None:
        """Initialize provider.

        Args:
            lookback_days: Only include PTRs filed within this many days.
            max_reports: Maximum number of PTR reports to fetch and parse.
            cache_dir: Directory to cache downloaded report HTML.
            timeout: HTTP request timeout in seconds.
            rate_limit_s: Sleep between report fetches (polite rate limiting).
        """
        self._lookback_days = lookback_days
        self._max_reports = max_reports
        self._cache_dir = Path(cache_dir)
        self._timeout = timeout
        self._rate_limit_s = rate_limit_s

        # Create cache directory if needed
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self) -> DisclosureFetch:
        """Fetch and parse Senate PTRs. Never raises — errors surface in .error."""
        trades: list[PoliticianTrade] = []
        errors: list[str] = []

        fetched_at = datetime.now(timezone.utc).isoformat()

        # Step 1: Accept agreement gate
        try:
            cookie_jar = self._accept_agreement()
        except Exception as exc:
            msg = f"Failed to accept agreement gate: {exc}"
            log.warning(msg)
            return DisclosureFetch(
                trades=[],
                fetched_at=fetched_at,
                source="senate_efd",
                error=msg,
            )

        # Step 2: Search for recent PTRs
        try:
            reports = self._search_reports(cookie_jar)
        except Exception as exc:
            msg = f"Failed to search Senate PTRs: {exc}"
            log.warning(msg)
            return DisclosureFetch(
                trades=[],
                fetched_at=fetched_at,
                source="senate_efd",
                error=msg,
            )

        if not reports:
            log.info(f"No Senate PTRs found within {self._lookback_days} days")
            return DisclosureFetch(
                trades=[],
                fetched_at=fetched_at,
                source="senate_efd",
                error=None,
            )

        # Cap at max_reports
        reports = reports[:self._max_reports]

        # Step 3: Fetch and parse reports
        for idx, report in enumerate(reports):
            try:
                # Extract report details
                first_name = report.get("first_name", "")
                last_name = report.get("last_name", "")
                office = report.get("office", "unknown")
                date_filed_str = report.get("date_filed", "")
                uuid = report.get("uuid", "")

                if not uuid:
                    continue

                politician_name = f"{first_name} {last_name}".strip() or "unknown"
                source_url = _SENATE_PTR_DETAIL_TEMPLATE.format(uuid=uuid)

                # Fetch or load from cache
                html = self._fetch_report_html(uuid, cookie_jar)

                # Parse transactions
                trades_from_html = parse_senate_ptr_html(
                    html,
                    date_filed=date_filed_str,
                    politician=politician_name,
                    office=office,
                    source_url=source_url,
                )

                trades.extend(trades_from_html)
                log.debug(f"Parsed {len(trades_from_html)} trades from {politician_name} ({uuid})")

                # Rate limiting between fetches (but not for cached reports)
                if idx < len(reports) - 1:
                    time.sleep(self._rate_limit_s)

            except Exception as exc:
                msg = f"Failed to process Senate PTR {report.get('uuid', '?')}: {exc}"
                log.warning(msg)
                errors.append(msg)
                continue

        error_str = "; ".join(errors) if errors else None

        return DisclosureFetch(
            trades=trades,
            fetched_at=fetched_at,
            source="senate_efd",
            error=error_str,
        )

    def _accept_agreement(self) -> CookieJar:
        """Accept Senate eFD agreement gate.

        Returns a CookieJar with session + agreement cookies.
        Raises on network or CSRF extraction error.
        """
        cookie_jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

        # Step 1: GET home page, extract CSRF token
        req = urllib.request.Request(
            _SENATE_HOME_URL,
            headers={"User-Agent": _USER_AGENT},
        )
        with opener.open(req, timeout=self._timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extract CSRF token from hidden input
        csrf_match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
        if not csrf_match:
            raise ValueError("CSRF token not found in Senate home page")

        csrf_token = csrf_match.group(1)

        # Step 2: POST agreement acceptance
        post_data = f"csrfmiddlewaretoken={csrf_token}&prohibition_agreement=1".encode("utf-8")
        req = urllib.request.Request(
            _SENATE_HOME_URL,
            data=post_data,
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": _SENATE_HOME_URL,
            },
        )
        with opener.open(req, timeout=self._timeout) as resp:
            resp.read()  # Consume response (we just need the cookie)

        return cookie_jar

    def _search_reports(self, cookie_jar: CookieJar) -> list[dict]:
        """Search for recent Senate PTRs.

        Returns list of report dicts with keys: uuid, first_name, last_name,
        office, date_filed, report_type_html.
        Raises on network or parse error.
        """
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

        # Calculate date range
        today = date.today()
        start_date = today - timedelta(days=self._lookback_days)

        # Build AJAX request body (JSON would be cleaner, but form data is more robust)
        post_data = (
            f"draw=1&start=0&length={self._max_reports}&"
            f"report_types=11&"  # 11 = Periodic Transaction Report
            f"dtServerStart={start_date.isoformat()}&"
            f"dtServerEnd={today.isoformat()}"
        ).encode("utf-8")

        req = urllib.request.Request(
            _SENATE_SEARCH_AJAX_URL,
            data=post_data,
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": _SENATE_HOME_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        with opener.open(req, timeout=self._timeout) as resp:
            response_text = resp.read().decode("utf-8")

        # Parse response (expect JSON with "data" array)
        import json
        try:
            response_json = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse Senate AJAX response as JSON: {exc}")

        data_rows = response_json.get("data", [])

        reports = []
        for row in data_rows:
            if not isinstance(row, list) or len(row) < 5:
                continue

            # Row format: [first, last, office, report_type_html, date_filed]
            first_name = row[0].strip() if row[0] else ""
            last_name = row[1].strip() if row[1] else ""
            office = row[2].strip() if row[2] else ""
            report_type_html = row[3].strip() if row[3] else ""
            date_filed = row[4].strip() if row[4] else ""

            # Extract UUID from <a href="/search/view/ptr/{uuid}/">
            uuid_match = re.search(r'/search/view/ptr/([a-f0-9-]+)/', report_type_html)
            if not uuid_match:
                continue

            uuid = uuid_match.group(1)

            reports.append({
                "uuid": uuid,
                "first_name": first_name,
                "last_name": last_name,
                "office": office,
                "date_filed": date_filed,
                "report_type_html": report_type_html,
            })

        return reports

    def _fetch_report_html(self, uuid: str, cookie_jar: CookieJar) -> str:
        """Fetch PTR report HTML. Uses cache if available, otherwise downloads.

        Returns HTML content as string.
        Raises on network or file error.
        """
        cache_path = self._cache_dir / f"{uuid}.html"

        # Check cache first
        if cache_path.exists():
            log.debug(f"Loading cached report: {uuid}")
            return cache_path.read_text(encoding="utf-8")

        # Download
        report_url = _SENATE_PTR_DETAIL_TEMPLATE.format(uuid=uuid)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

        req = urllib.request.Request(
            report_url,
            headers={
                "User-Agent": _USER_AGENT,
                "Referer": _SENATE_HOME_URL,
            },
        )

        with opener.open(req, timeout=self._timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Cache it
        cache_path.write_text(html, encoding="utf-8")
        log.debug(f"Cached report: {uuid}")

        return html
