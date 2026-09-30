"""Tests for DiscoveryLagCalculator."""
from __future__ import annotations

import pytest
from equities.research.discovery_lag import DiscoveryLagCalculator


class _StubLag(DiscoveryLagCalculator):
    def _fetch_return(self, ticker: str, period: str = "1y") -> float | None:
        returns = {
            "1y": {"NVDA": 150.0, "COHR": 40.0, "MU": 80.0},
            "3mo": {"NVDA": 35.0, "COHR": 12.0, "MU": 20.0},
            "1mo": {"NVDA": 20.0, "COHR": 5.0, "MU": 10.0},
        }
        return returns.get(period, {}).get(ticker)

    def _fetch_12m_return(self, ticker: str) -> float | None:
        returns = {"NVDA": 150.0, "COHR": 40.0, "MU": 80.0}
        return returns.get(ticker)


def test_lag_is_trunk_minus_leaf():
    calc = _StubLag()
    assert calc.compute("NVDA", "COHR") == pytest.approx(110.0)


def test_missing_ticker_returns_no_signal():
    calc = _StubLag()
    assert calc.compute("NVDA", "UNKN") is None


def test_lag_supports_shorter_periods():
    calc = _StubLag()
    assert calc.compute("NVDA", "COHR", period="1mo") == pytest.approx(15.0)


def test_lag_supports_strategy_periods():
    calc = _StubLag()
    assert calc.compute("NVDA", "COHR", period="1y") == pytest.approx(110.0)
    assert calc.compute("NVDA", "COHR", period="3mo") == pytest.approx(23.0)
    assert calc.compute("NVDA", "COHR", period="1mo") == pytest.approx(15.0)


def test_yfinance_history_requests_adjusted_prices(monkeypatch):
    calls = {}

    class History:
        @staticmethod
        def history(**kwargs):
            calls.update(kwargs)
            return type("Frame", (), {"empty": True})()

    class YF:
        @staticmethod
        def Ticker(_ticker):
            return History()

    monkeypatch.setitem(__import__("sys").modules, "yfinance", YF)
    assert DiscoveryLagCalculator()._fetch_return("NVDA") is None
    assert calls["auto_adjust"] is True
