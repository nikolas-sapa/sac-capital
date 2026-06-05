"""Tests for DiscoveryLagCalculator."""
from __future__ import annotations

import pytest
from equities.research.discovery_lag import DiscoveryLagCalculator


class _StubLag(DiscoveryLagCalculator):
    def _fetch_12m_return(self, ticker: str) -> float | None:
        returns = {"NVDA": 150.0, "COHR": 40.0, "MU": 80.0}
        return returns.get(ticker)


def test_lag_is_trunk_minus_leaf():
    calc = _StubLag()
    assert calc.compute("NVDA", "COHR") == pytest.approx(110.0)


def test_missing_ticker_returns_zero():
    calc = _StubLag()
    assert calc.compute("NVDA", "UNKN") == 0.0
