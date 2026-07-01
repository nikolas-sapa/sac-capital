"""Tests for bounded timeout guards in SEC filings provider."""
from unittest.mock import patch, MagicMock

import httpx
import pytest

from equities.data.filings import SECEdgarFilings, Filing


class TestFilingsTimeout:
    """Test timeout behavior in SECEdgarFilings."""

    def test_recent_submissions_timeout_returns_empty(self):
        """When SEC submissions API times out, return empty list."""
        filings = SECEdgarFilings()

        with patch("equities.data.filings._ticker_to_cik") as mock_cik:
            mock_cik.return_value = 789019  # AAPL CIK
            with patch("httpx.get") as mock_get:
                mock_get.side_effect = httpx.TimeoutException("Connection timed out")
                result = filings.recent("AAPL", days=30)
                assert result == []

    def test_recent_no_cik_returns_empty(self):
        """When CIK lookup fails, return empty list without making HTTP call."""
        filings = SECEdgarFilings()

        with patch("equities.data.filings._ticker_to_cik") as mock_cik:
            mock_cik.return_value = None
            with patch("httpx.get") as mock_get:
                result = filings.recent("INVALID", days=30)
                assert result == []
                # Verify no HTTP call was made
                mock_get.assert_not_called()

    def test_company_ticker_map_timeout_returns_empty(self):
        """When ticker map API times out, return empty mapping."""
        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Ticker map timed out")
            # Call the function directly (bypassing the cache for this test)
            from equities.data.filings import _company_ticker_map

            # Clear the cache
            _company_ticker_map.cache_clear()
            result = _company_ticker_map()
            assert result == {}

    def test_recent_valid_response(self):
        """Verify normal operation with valid SEC response."""
        from datetime import date, timedelta

        filings = SECEdgarFilings()

        # Use dates within the last 30 days
        today = date.today()
        recent_date = (today - timedelta(days=5)).isoformat()

        with patch("equities.data.filings._ticker_to_cik") as mock_cik:
            mock_cik.return_value = 789019
            with patch("httpx.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "filings": {
                        "recent": {
                            "form": ["8-K", "10-Q"],
                            "filingDate": [recent_date, "2024-12-15"],
                            "items": ["2.02", ""],
                        }
                    }
                }
                mock_get.return_value = mock_resp

                result = filings.recent("AAPL", days=30)
                assert len(result) > 0
                assert result[0].form_type in ("8-K", "10-Q")
