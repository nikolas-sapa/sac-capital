"""Tests for bounded timeout guards in Tiingo news provider."""
from unittest.mock import patch, MagicMock

import httpx
import pytest

from equities.data.news_tiingo import TiingoNewsProvider


class TestTiingoTimeout:
    """Test timeout behavior in TiingoNewsProvider."""

    def test_headlines_timeout_returns_empty(self):
        """When Tiingo API times out, return empty list."""
        provider = TiingoNewsProvider(api_key="test-key")

        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            result = provider.headlines("AAPL", limit=15)
            assert result == []

    def test_headlines_no_key_returns_empty(self):
        """When API key is missing, return empty list without making request."""
        provider = TiingoNewsProvider(api_key=None)

        with patch("httpx.get") as mock_get:
            result = provider.headlines("AAPL", limit=15)
            assert result == []
            # Verify no HTTP call was made
            mock_get.assert_not_called()

    def test_headlines_http_error_returns_empty(self):
        """When Tiingo API returns error, return empty list."""
        provider = TiingoNewsProvider(api_key="test-key")

        with patch("httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
            mock_get.return_value = mock_resp

            result = provider.headlines("INVALID", limit=15)
            assert result == []

    def test_headlines_valid_response(self):
        """Verify normal operation with valid Tiingo response."""
        provider = TiingoNewsProvider(api_key="test-key")

        with patch("httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = [
                {
                    "title": "Apple Q1 Earnings Beat",
                    "description": "Apple reported strong Q1 results with 15% YoY growth.",
                },
                {
                    "title": "iPhone 16 Pro Announcement",
                    "description": "Apple unveiled the new iPhone 16 Pro with AI features.",
                },
            ]
            mock_get.return_value = mock_resp

            result = provider.headlines("AAPL", limit=2)
            assert len(result) == 2
            assert "Apple Q1 Earnings Beat" in result[0]
            assert "iPhone 16 Pro Announcement" in result[1]

    def test_headlines_empty_response(self):
        """When Tiingo returns empty list, return empty result."""
        provider = TiingoNewsProvider(api_key="test-key")

        with patch("httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = []
            mock_get.return_value = mock_resp

            result = provider.headlines("UNKNOWN", limit=15)
            assert result == []
