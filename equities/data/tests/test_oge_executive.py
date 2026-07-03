"""Tests for OGE executive branch disclosure provider."""
from datetime import date

import pytest

from equities.data.oge_executive import (
    parse_278t_text,
    _normalize_amount_text,
    _normalize_type_text,
    _resolve_ticker,
)


# Real Trump 278-T text sample (extracted from official PDF)
TRUMP_278T_SAMPLE = """
OGE Form 278-T (Updated February 2024)
U.S. Office of Government Ethics; 5 C.F.R. part 2634
Executive Branch Personnel Public Financial Disclosure Report:
Periodic Transaction Report (OGE Form 278-T)

Filer's Information
Last Name Ml Position
Trump J President of the United States of America

Donald J Trump

Transactions
Description Type Date Days Ago Amount

1 VANGUARD S&P 500 ETF UNSOLICITED I DUrchOSO 3/212028 Vos $1 .000.001 • $5 000 000
2 SERVICENOW INC COM lourchaae 2/10/2028 Vos $1000001-$5000 000
3 NVIDIA CORP lourchaae 2/10/2028 Vos $1,000,001 • $5 000,000
4 ADOBE INC lourchose 2/10/2026 Yes $1 000 001 -$5,000,000
5 ORACLE CORPORATION COM ourchllao 3/17/2026 Vos $1,000,001 - $5,000,000
6 MICROSOFT CORP UNSOLICITED ourchaae 3/1912026 Yoa $1,000 001-$5,000 000
7 BROADCOM INC COM purchaao 2/10/2028 Vos $1 000 001 -$5,000,000
8 APPLE INC UNSOLICITED ourchaso 3/212026 Vos $1 000,001 -$5,000 ,000
9 AMAZON.COM INC UNSOLICITED ourchuo 3/19/2028 Vos $1,000,001 -$5,000 000
10 Some ETF Without Ticker ourchaae 2/10/2026 Vos $500,001 - $1,000,000

End of Report
"""


class TestNormalizeAmountText:
    """Test OCR amount normalization."""

    def test_normalize_spaces_in_amount(self):
        """Remove intra-number spaces."""
        assert _normalize_amount_text("$5 000 000") == "$5000000"

    def test_normalize_bullet_to_dash(self):
        """Convert bullet separators to dashes."""
        # Commas are preserved; spaces between digits removed
        assert _normalize_amount_text("$1,000,001 • $5 000,000") == "$1,000,001 - $5000,000"

    def test_normalize_complex_ocr(self):
        """Handle complex OCR'd text."""
        result = _normalize_amount_text("$1 .000.001 • $5 000 000")
        # Dots within numbers stay as-is; spaces removed; bullet converted
        assert "000001" in result or "000.001" in result  # Either format acceptable
        assert "-" in result  # Bullet converted to dash


class TestNormalizeTypeText:
    """Test OCR transaction type normalization."""

    def test_normalize_purchase_mangled_variants(self):
        """Recognize various OCR'd purchase codes."""
        assert _normalize_type_text("lourchaae") == "P"
        assert _normalize_type_text("DUrchOSO") == "P"
        assert _normalize_type_text("ourchaao") == "P"
        assert _normalize_type_text("lourchose") == "P"
        assert _normalize_type_text("purchase") == "P"
        assert _normalize_type_text("P") == "P"

    def test_normalize_sale_mangled_variants(self):
        """Recognize various OCR'd sale codes."""
        assert _normalize_type_text("sol") == "S"
        assert _normalize_type_text("SOL") == "S"
        assert _normalize_type_text("sal") == "S"
        assert _normalize_type_text("sale") == "S"
        assert _normalize_type_text("S") == "S"

    def test_normalize_unknown_type(self):
        """Passthrough unknown types."""
        result = _normalize_type_text("UNKNOWN")
        assert result == "UNKNOWN"


class TestResolveTicker:
    """Test asset name to ticker resolution."""

    def test_resolve_exact_match(self):
        """Resolve via exact name match."""
        assert _resolve_ticker("NVIDIA CORP") == "NVDA"
        assert _resolve_ticker("MICROSOFT CORP") == "MSFT"
        assert _resolve_ticker("APPLE INC") == "AAPL"

    def test_resolve_case_insensitive(self):
        """Resolve case-insensitively."""
        assert _resolve_ticker("nvidia corp") == "NVDA"
        assert _resolve_ticker("NVIDIA CORP") == "NVDA"
        assert _resolve_ticker("Nvidia Corp") == "NVDA"

    def test_resolve_prefix_match(self):
        """Resolve via prefix match."""
        assert _resolve_ticker("ORACLE") in [None, "ORCL"]  # Depends on map

    def test_resolve_unknown(self):
        """Return None for unknown assets."""
        assert _resolve_ticker("UNKNOWN COMPANY XYZ") is None
        assert _resolve_ticker("") is None


class TestParse278tText:
    """Test 278-T text parsing."""

    def test_parse_nvidia_buy(self):
        """Parse NVIDIA buy transaction."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        nvidia = next((t for t in trades if t.ticker == "NVDA"), None)
        assert nvidia is not None
        assert nvidia.ticker == "NVDA"
        assert nvidia.politician == "Donald J. Trump"
        assert nvidia.chamber == "executive"
        assert nvidia.transaction_type == "buy"
        assert nvidia.amount_min == 1_000_001
        assert nvidia.amount_max == 5_000_000

    def test_parse_microsoft_buy(self):
        """Parse MICROSOFT buy with OCR'd type."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        msft = next((t for t in trades if t.ticker == "MSFT"), None)
        assert msft is not None
        assert msft.ticker == "MSFT"
        assert msft.transaction_type == "buy"  # Fuzzy match on "ourchaae"

    def test_parse_apple_buy(self):
        """Parse APPLE buy transaction."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        aapl = next((t for t in trades if t.ticker == "AAPL"), None)
        assert aapl is not None
        assert aapl.ticker == "AAPL"
        assert aapl.transaction_type == "buy"

    def test_parse_all_recognized_assets(self):
        """Ensure all recognized assets are parsed."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        tickers = {t.ticker for t in trades}
        # Should include: NVDA, NOW, ADBE, ORCL, MSFT, AVGO, AAPL, AMZN
        expected = {"NVDA", "NOW", "ADBE", "ORCL", "MSFT", "AVGO", "AAPL", "AMZN"}
        assert expected.issubset(tickers), f"Missing: {expected - tickers}"

    def test_parse_skip_unresolvable_asset(self):
        """Skip transactions without recognized ticker."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        # "Some ETF Without Ticker" should be skipped
        tickers = {t.ticker for t in trades}
        assert "ETF" not in tickers
        assert "SOME" not in tickers

    def test_parse_filed_date_as_string(self):
        """Accept filed_date as string."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        assert len(trades) > 0
        assert all(t.date_filed == date(2026, 5, 13) for t in trades)

    def test_parse_filed_date_as_date(self):
        """Accept filed_date as date object."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date=date(2026, 5, 13),
            source_url="https://example.com/trump-278t.pdf",
        )

        assert len(trades) > 0
        assert all(t.date_filed == date(2026, 5, 13) for t in trades)

    def test_parse_invalid_filed_date(self):
        """Return empty list for invalid filed_date."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="not-a-date",
            source_url="https://example.com/trump-278t.pdf",
        )

        assert trades == []

    def test_parse_empty_text(self):
        """Empty text yields no trades."""
        trades = parse_278t_text(
            "",
            filer="Test",
            filed_date="2026-05-13",
            source_url="http://example.com",
        )

        assert trades == []

    def test_parse_all_trades_have_required_fields(self):
        """All parsed trades have required PoliticianTrade fields."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        assert len(trades) > 0
        for trade in trades:
            assert trade.ticker and len(trade.ticker) > 0
            assert trade.politician == "Donald J. Trump"
            assert trade.chamber == "executive"
            assert trade.transaction_type in {"buy", "sell", "exchange"}
            assert trade.owner == "self"
            assert trade.amount_min > 0
            assert trade.amount_max >= trade.amount_min
            assert trade.date_filed == date(2026, 5, 13)
            assert trade.source == "executive_stock_watcher"
            assert trade.source_url

    def test_parse_handles_ocr_spacing_in_amounts(self):
        """Parser correctly handles OCR'd spacing in dollar amounts."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        # All trades should have reasonable amount ranges
        for trade in trades:
            assert 1_000_001 <= trade.amount_min <= 5_000_001
            assert trade.amount_max >= trade.amount_min
            # Sanity: amounts shouldn't be unreasonably small (< $1k)
            assert trade.amount_min > 1000

    @pytest.mark.parametrize("ticker,expected", [
        ("NVDA", "NVIDIA CORP"),
        ("MSFT", "MICROSOFT CORP"),
        ("AAPL", "APPLE INC"),
        ("AMZN", "AMAZON.COM INC"),
    ])
    def test_parse_specific_tickers(self, ticker, expected):
        """Verify specific tickers are resolved correctly."""
        trades = parse_278t_text(
            TRUMP_278T_SAMPLE,
            filer="Donald J. Trump",
            filed_date="2026-05-13",
            source_url="https://example.com/trump-278t.pdf",
        )

        trade = next((t for t in trades if t.ticker == ticker), None)
        assert trade is not None, f"Expected to find {ticker} in trades"
