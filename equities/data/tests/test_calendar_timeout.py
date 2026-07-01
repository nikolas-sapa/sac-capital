"""Tests for bounded timeout guards in calendar provider."""
from unittest.mock import patch, MagicMock
from datetime import date
import sys

import pytest

# Mock yfinance before importing calendar
sys.modules['yfinance'] = MagicMock()

from equities.data.calendar import YFinanceCalendar, EarningsSnapshot


class TestCalendarTimeout:
    """Test timeout behavior in YFinanceCalendar."""

    def test_fetch_timeout_returns_empty_snapshot(self):
        """When yfinance.Ticker() times out, return empty snapshot."""
        calendar = YFinanceCalendar()
        with patch("equities.data.calendar.call_quietly") as mock_call:
            mock_call.side_effect = TimeoutError("Hung connection")
            result = calendar.fetch("AAPL")
            assert result.ticker == "AAPL"
            assert result.next_earnings_date is None
            assert result.last_surprise_pct is None

    def test_next_date_timeout_returns_none(self):
        """When calendar fetch times out, return None."""
        calendar = YFinanceCalendar()
        mock_ticker = MagicMock()

        with patch("equities.data.calendar.call_quietly") as mock_call:
            # First call (t.calendar) times out
            mock_call.side_effect = TimeoutError("Hung calendar request")
            result = calendar._next_date(mock_ticker)
            assert result is None

    def test_last_surprise_timeout_returns_none(self):
        """When earnings history fetch times out, return None."""
        calendar = YFinanceCalendar()
        mock_ticker = MagicMock()

        with patch("equities.data.calendar.call_quietly") as mock_call:
            # earnings_history fetch times out
            mock_call.side_effect = TimeoutError("Hung earnings history request")
            result = calendar._last_surprise(mock_ticker)
            assert result is None

    def test_fetch_partial_data_on_one_timeout(self):
        """When one data fetch times out, other data may still load."""
        calendar = YFinanceCalendar()
        mock_ticker = MagicMock()

        with patch("equities.data.calendar.call_quietly") as mock_call:
            # First call succeeds (next_date), second call times out (surprise)
            mock_call.side_effect = [
                {"Earnings Date": [date(2025, 1, 15)]},  # calendar succeeds
                TimeoutError("Hung earnings history"),   # surprise times out
            ]
            next_date = calendar._next_date(mock_ticker)
            assert next_date == date(2025, 1, 15)

            last_surprise = calendar._last_surprise(mock_ticker)
            assert last_surprise is None
