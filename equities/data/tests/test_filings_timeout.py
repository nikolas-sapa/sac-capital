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
        from equities.data.filings import _company_ticker_map, _TICKER_MAP_CACHE

        _TICKER_MAP_CACHE.clear()
        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Ticker map timed out")
            result = _company_ticker_map()
            assert result == {}

    def test_failed_ticker_map_is_not_cached(self):
        """A failed fetch must not poison the cache for the rest of the run.

        Regression: @lru_cache pinned the empty mapping process-wide, so every
        filings-based screen silently returned zero candidates all run with
        provider_failures=0.
        """
        from equities.data.filings import _company_ticker_map, _TICKER_MAP_CACHE

        _TICKER_MAP_CACHE.clear()
        try:
            with patch("httpx.get") as mock_get:
                mock_get.side_effect = httpx.TimeoutException("boom")
                assert _company_ticker_map() == {}

            # Second call, network healthy again — must re-fetch, not serve {}.
            with patch("httpx.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "0": {"ticker": "PLTR", "cik_str": 1321655},
                }
                mock_get.return_value = mock_resp
                assert _company_ticker_map() == {"PLTR": 1321655}
        finally:
            _TICKER_MAP_CACHE.clear()

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
