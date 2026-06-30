"""Politician STOCK Act disclosure signals — Senate PTR (Periodic Transaction Report) filings.

Official source: Senate eFilings Disclosure (eFD)
https://efdsearch.senate.gov/search/home/

Flow:
1. Launch headless Chromium (via Playwright)
2. Navigate to home page, accept agreement checkbox
3. Submit to unlock search (sets agreement cookie via WAF)
4. Drive AJAX search for recent PTRs (report_types=[11], date range)
5. For each recent PTR, fetch and parse HTML table of transactions

IMPORTANT: Senate PTRs rendered electronically use HTML tables. Older PDFs may not be supported.
Partial results are valid. Never raises — all errors surface in DisclosureFetch.error.
Playwright is lazy-imported inside fetch() so the module imports fine without it.
"""
from __future__ import annotations

import html.parser
import io
import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
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
        headless: bool = True,
    ) -> None:
        """Initialize provider.

        Args:
            lookback_days: Only include PTRs filed within this many days.
            max_reports: Maximum number of PTR reports to fetch and parse.
            cache_dir: Directory to cache downloaded report HTML.
            timeout: HTTP request timeout in seconds.
            rate_limit_s: Sleep between report fetches (polite rate limiting).
            headless: Run Chromium in headless mode (no UI).
        """
        self._lookback_days = lookback_days
        self._max_reports = max_reports
        self._cache_dir = Path(cache_dir)
        self._timeout = timeout
        self._rate_limit_s = rate_limit_s
        self._headless = headless

        # Create cache directory if needed
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self) -> DisclosureFetch:
        """Fetch and parse Senate PTRs via Playwright browser. Never raises — errors surface in .error."""
        # Lazy-import Playwright so module imports fine without it
        from playwright.sync_api import sync_playwright

        trades: list[PoliticianTrade] = []
        errors: list[str] = []
        fetched_at = datetime.now(timezone.utc).isoformat()

        browser = None
        context = None
        page = None

        try:
            # Launch browser and navigate through agreement gate
            with sync_playwright() as p:
                # Anti-bot-detection: Akamai challenges headless Chromium. These
                # reduce the signals it fingerprints. Headful (headless=False)
                # passes far more reliably from a flagged IP.
                browser = p.chromium.launch(
                    headless=self._headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={"width": 1280, "height": 900},
                    locale="en-US",
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = context.new_page()

                # Step 1: Accept agreement gate
                try:
                    self._accept_agreement_browser(page)
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
                    reports = self._search_reports_browser(page)
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
                        html = self._fetch_report_html_browser(page, uuid)

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

        except Exception as exc:
            # Catch any uncaught exception from the with block
            msg = f"Browser error during Senate eFD fetch: {exc}"
            log.warning(msg)
            if not errors:
                errors.append(msg)
        finally:
            # Ensure browser is closed
            if browser:
                try:
                    browser.close()
                except Exception as exc:
                    log.debug(f"Error closing browser: {exc}")

        error_str = "; ".join(errors) if errors else None

        return DisclosureFetch(
            trades=trades,
            fetched_at=fetched_at,
            source="senate_efd",
            error=error_str,
        )

    def _accept_agreement_browser(self, page) -> None:
        """Accept Senate eFD agreement gate via browser.

        Navigates to home page, accepts the agreement checkbox, and submits.
        This sets the session + agreement cookies that unlock the search.
        Raises on navigation or interaction error.
        """
        # Confirmed live markup: <input type="checkbox" id="agree_statement"
        # name="prohibition_agreement" value="1">. The WAF (Akamai) sometimes
        # serves a JS challenge page first, so retry the nav until the real
        # checkbox actually appears rather than failing on the challenge page.
        checkbox_selector = "#agree_statement"
        last_exc = None
        for attempt in range(3):
            page.goto(_SENATE_HOME_URL, timeout=int(self._timeout * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=int(self._timeout * 1000))
            except Exception:
                pass  # networkidle can hang on analytics long-polls; the wait below is what matters
            try:
                page.wait_for_selector(checkbox_selector, state="visible",
                                       timeout=int(self._timeout * 1000))
                break
            except Exception as exc:
                last_exc = exc
                log.debug("Agreement checkbox not visible (attempt %d); likely WAF challenge, retrying", attempt + 1)
        else:
            raise ValueError(f"Agreement checkbox never appeared (WAF challenge?): {last_exc}")

        # force=True bypasses strict actionability checks for the old-markup checkbox
        try:
            page.check(checkbox_selector, force=True, timeout=int(self._timeout * 1000))
            log.debug("Checked agreement checkbox")
        except Exception as exc:
            raise ValueError(f"Failed to check agreement checkbox: {exc}")

        # Submit the form (typically a button or form submission)
        # Wait for any form to be present and submit it
        try:
            # Try to find and click a submit button, or just submit the form
            submit_selector = 'button[type="submit"]'
            if page.query_selector(submit_selector):
                page.click(submit_selector, timeout=int(self._timeout * 1000))
                log.debug("Clicked submit button")
            else:
                # Alternative: submit the form directly
                page.evaluate('document.querySelector("form").submit()')
                log.debug("Submitted form via JavaScript")

            # Wait for navigation to complete (agreement accepted)
            page.wait_for_load_state("networkidle")
            log.debug("Agreement gate accepted")
        except Exception as exc:
            raise ValueError(f"Failed to submit agreement: {exc}")

    def _search_reports_browser(self, page) -> list[dict]:
        """Search for recent Senate PTRs via browser's API request.

        Uses page.request to make AJAX call, which carries browser's cookies
        and passes the WAF. Returns list of report dicts with keys: uuid,
        first_name, last_name, office, date_filed, report_type_html.
        Raises on network or parse error.
        """
        # Calculate date range
        today = date.today()
        start_date = today - timedelta(days=self._lookback_days)

        # Build AJAX request body (form data format)
        post_data = (
            f"draw=1&start=0&length={self._max_reports}&"
            f"report_types=11&"  # 11 = Periodic Transaction Report
            f"dtServerStart={start_date.isoformat()}&"
            f"dtServerEnd={today.isoformat()}"
        )

        # Use page.request to make the AJAX call (carries browser cookies + passes WAF)
        response = page.request.post(
            _SENATE_SEARCH_AJAX_URL,
            data=post_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": _SENATE_HOME_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=int(self._timeout * 1000),
        )

        if not response.ok:
            raise ValueError(f"AJAX search returned {response.status}: {response.text()[:200]}")

        response_text = response.text()

        # Parse response (expect JSON with "data" array)
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

    def _fetch_report_html_browser(self, page, uuid: str) -> str:
        """Fetch PTR report HTML via browser. Uses cache if available, otherwise downloads.

        Returns HTML content as string.
        Raises on network or file error.
        """
        cache_path = self._cache_dir / f"{uuid}.html"

        # Check cache first
        if cache_path.exists():
            log.debug(f"Loading cached report: {uuid}")
            return cache_path.read_text(encoding="utf-8")

        # Download via browser's API request (carries cookies + passes WAF)
        report_url = _SENATE_PTR_DETAIL_TEMPLATE.format(uuid=uuid)
        response = page.request.get(
            report_url,
            timeout=int(self._timeout * 1000),
        )

        if not response.ok:
            raise ValueError(f"Failed to fetch report {uuid}: HTTP {response.status}")

        html = response.text()

        # Cache it
        cache_path.write_text(html, encoding="utf-8")
        log.debug(f"Cached report: {uuid}")

        return html
