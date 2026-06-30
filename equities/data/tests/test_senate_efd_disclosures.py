"""Tests for Senate eFD disclosure provider."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from equities.data.senate_efd_disclosures import parse_senate_ptr_html, SenateEFDDisclosureProvider


# Sample Senate PTR HTML table
SENATE_PTR_HTML_SAMPLE = """
<html>
<body>
<table>
<tr>
<td>TSLA</td>
<td>Buy</td>
<td>$1,000,001 - $5,000,000</td>
<td>05/15/2026</td>
<td>06/01/2026</td>
</tr>
<tr>
<td>MSFT</td>
<td>Sell</td>
<td>$500,001 - $1,000,000</td>
<td>05/10/2026</td>
<td>06/01/2026</td>
</tr>
<tr>
<td>--</td>
<td>Buy</td>
<td>$100,000 - $250,000</td>
<td>05/05/2026</td>
<td>06/01/2026</td>
</tr>
<tr>
<td>NVDA</td>
<td>Exchange</td>
<td>$2,000,001 - $5,000,000</td>
<td>05/20/2026</td>
<td>06/01/2026</td>
</tr>
</table>
</body>
</html>
"""


def test_parse_senate_ptr_html_tsla_buy():
    """Parse TSLA buy transaction."""
    trades = parse_senate_ptr_html(
        SENATE_PTR_HTML_SAMPLE,
        date_filed="06/01/2026",
        politician="John Smith",
        office="CA-01",
        source_url="https://efdsearch.senate.gov/search/view/ptr/abc123/",
    )

    tsla = next((t for t in trades if t.ticker == "TSLA"), None)
    assert tsla is not None
    assert tsla.ticker == "TSLA"
    assert tsla.transaction_type == "buy"
    assert tsla.amount_min == 1_000_001
    assert tsla.amount_max == 5_000_000
    assert tsla.transaction_date == date(2026, 5, 15)
    assert tsla.date_filed == date(2026, 6, 1)
    assert tsla.politician == "John Smith"
    assert tsla.chamber == "senate"
    assert tsla.owner == "self"


def test_parse_senate_ptr_html_msft_sell():
    """Parse MSFT sell transaction."""
    trades = parse_senate_ptr_html(
        SENATE_PTR_HTML_SAMPLE,
        date_filed="06/01/2026",
        politician="John Smith",
        office="CA-01",
        source_url="https://efdsearch.senate.gov/search/view/ptr/abc123/",
    )

    msft = next((t for t in trades if t.ticker == "MSFT"), None)
    assert msft is not None
    assert msft.ticker == "MSFT"
    assert msft.transaction_type == "sell"
    assert msft.amount_min == 500_001
    assert msft.amount_max == 1_000_000
    assert msft.date_filed == date(2026, 6, 1)


def test_parse_senate_ptr_html_nvda_exchange():
    """Parse NVDA exchange transaction."""
    trades = parse_senate_ptr_html(
        SENATE_PTR_HTML_SAMPLE,
        date_filed="06/01/2026",
        politician="John Smith",
        office="CA-01",
        source_url="https://efdsearch.senate.gov/search/view/ptr/abc123/",
    )

    nvda = next((t for t in trades if t.ticker == "NVDA"), None)
    assert nvda is not None
    assert nvda.ticker == "NVDA"
    assert nvda.transaction_type == "exchange"
    assert nvda.amount_min == 2_000_001
    assert nvda.amount_max == 5_000_000


def test_parse_senate_ptr_html_skip_no_ticker():
    """Skip transactions with no valid ticker (-- symbol)."""
    trades = parse_senate_ptr_html(
        SENATE_PTR_HTML_SAMPLE,
        date_filed="06/01/2026",
        politician="John Smith",
        office="CA-01",
        source_url="https://efdsearch.senate.gov/search/view/ptr/abc123/",
    )

    # Should have TSLA, MSFT, NVDA but NOT the -- transaction
    tickers = [t.ticker for t in trades]
    assert "TSLA" in tickers
    assert "MSFT" in tickers
    assert "NVDA" in tickers
    assert "--" not in tickers
    assert len(tickers) == 3


def test_parse_senate_ptr_html_empty_text():
    """Empty HTML yields no trades."""
    trades = parse_senate_ptr_html(
        "",
        date_filed="06/01/2026",
        politician="John Smith",
        office="CA-01",
        source_url="http://example.com",
    )
    assert trades == []


def test_parse_senate_ptr_html_invalid_filed_date():
    """Invalid filed_date yields no trades."""
    trades = parse_senate_ptr_html(
        SENATE_PTR_HTML_SAMPLE,
        date_filed="not-a-date",
        politician="John Smith",
        office="CA-01",
        source_url="http://example.com",
    )
    assert trades == []


def test_parse_senate_ptr_html_filed_date_as_date_object():
    """filed_date can be a date object."""
    trades = parse_senate_ptr_html(
        SENATE_PTR_HTML_SAMPLE,
        date_filed=date(2026, 6, 1),
        politician="John Smith",
        office="CA-01",
        source_url="https://efdsearch.senate.gov/search/view/ptr/abc123/",
    )

    assert len(trades) == 3
    assert all(t.date_filed == date(2026, 6, 1) for t in trades)


def test_parse_senate_ptr_html_malformed_table():
    """Malformed table (missing columns) is skipped gracefully."""
    html = """
    <html>
    <body>
    <table>
    <tr>
    <td>AAPL</td>
    <td>Buy</td>
    </tr>
    </table>
    </body>
    </html>
    """
    trades = parse_senate_ptr_html(
        html,
        date_filed="06/01/2026",
        politician="Test Person",
        office="TX-01",
        source_url="http://example.com",
    )
    # Malformed row should be skipped
    assert len(trades) == 0


def test_parse_senate_ptr_html_case_insensitive_ticker():
    """Ticker parsing is case-insensitive."""
    html = """
    <html>
    <body>
    <table>
    <tr>
    <td>aapl</td>
    <td>buy</td>
    <td>$50,000 - $100,000</td>
    <td>05/01/2026</td>
    <td>06/01/2026</td>
    </tr>
    </table>
    </body>
    </html>
    """
    trades = parse_senate_ptr_html(
        html,
        date_filed="06/01/2026",
        politician="Test Person",
        office="TX-01",
        source_url="http://example.com",
    )

    assert len(trades) == 1
    assert trades[0].ticker == "AAPL"  # Normalized to uppercase


@patch("equities.data.senate_efd_disclosures.urllib.request.build_opener")
def test_fetch_never_raises_on_agreement_failure(mock_opener):
    """Provider.fetch() never raises — errors surface in .error."""
    mock_opener.side_effect = Exception("Network error")

    provider = SenateEFDDisclosureProvider(lookback_days=30)
    result = provider.fetch()

    assert result.trades == []
    assert result.source == "senate_efd"
    assert result.error is not None
    assert "Failed to accept agreement" in result.error


@patch("equities.data.senate_efd_disclosures.urllib.request.build_opener")
def test_fetch_never_raises_on_search_failure(mock_opener):
    """Provider.fetch() never raises even if search fails."""
    provider = SenateEFDDisclosureProvider(lookback_days=30)

    # Mock all opener calls to fail at search stage
    mock_opener_instance = MagicMock()
    mock_opener.return_value = mock_opener_instance

    # Setup first call (agreement home page GET) to succeed
    get_response = MagicMock()
    get_response.read.return_value = b'<input name="csrfmiddlewaretoken" value="csrf123">'
    get_response.__enter__ = MagicMock(return_value=get_response)
    get_response.__exit__ = MagicMock(return_value=False)

    # Setup second call (agreement POST) to succeed
    post_response = MagicMock()
    post_response.read.return_value = b''
    post_response.__enter__ = MagicMock(return_value=post_response)
    post_response.__exit__ = MagicMock(return_value=False)

    # Setup third call (search) to fail
    mock_opener_instance.open.side_effect = [
        get_response,
        post_response,
        Exception("Network timeout on search"),
    ]

    result = provider.fetch()

    # Provider should never raise, error should be captured
    assert result.trades == []
    assert result.source == "senate_efd"
    assert result.error is not None
    assert "Failed to search" in result.error or "Network timeout" in result.error


def test_fetch_handles_empty_search_results():
    """Provider.fetch() handles empty search results gracefully."""
    provider = SenateEFDDisclosureProvider(lookback_days=30)

    with patch.object(provider, "_accept_agreement") as mock_accept:
        with patch.object(provider, "_search_reports") as mock_search:
            mock_accept.return_value = MagicMock()
            mock_search.return_value = []

            result = provider.fetch()

            assert result.trades == []
            assert result.source == "senate_efd"
            assert result.error is None


def test_fetch_caps_reports_at_max():
    """Provider.fetch() respects max_reports limit."""
    provider = SenateEFDDisclosureProvider(lookback_days=30, max_reports=3)

    # Create mock reports (more than max_reports)
    mock_reports = [
        {
            "uuid": f"uuid-{i}",
            "first_name": "John",
            "last_name": f"Doe{i}",
            "office": f"STATE-{i}",
            "date_filed": "2026-06-01",
        }
        for i in range(5)
    ]

    with patch.object(provider, "_accept_agreement") as mock_accept:
        with patch.object(provider, "_search_reports") as mock_search:
            with patch.object(provider, "_fetch_report_html") as mock_fetch:
                mock_accept.return_value = MagicMock()
                mock_search.return_value = mock_reports
                mock_fetch.return_value = "<html><table></table></html>"

                result = provider.fetch()

                # Should only attempt to fetch 3 reports (max_reports)
                assert mock_fetch.call_count == 3


def test_provider_creates_cache_directory():
    """Provider.__init__() creates cache directory."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "senate_cache" / "subdir"
        assert not cache_path.exists()

        provider = SenateEFDDisclosureProvider(cache_dir=str(cache_path))

        assert cache_path.exists()
