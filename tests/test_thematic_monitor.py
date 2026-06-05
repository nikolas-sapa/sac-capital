"""Tests for ThematicMonitor."""
from __future__ import annotations

from equities.screen.thematic_monitor import ThematicMonitor


def test_no_concentration_no_alerts():
    monitor = ThematicMonitor(max_theme_pct=0.35, capital=100_000)
    open_positions = [
        {"ticker": "MU",   "shares": 100, "entry_price": 100.0},   # $10k NVDA chain
        {"ticker": "COHR", "shares": 80,  "entry_price": 80.0},    # $6.4k NVDA chain
        {"ticker": "CRWD", "shares": 50,  "entry_price": 200.0},   # $10k MSFT chain
    ]
    assert monitor.check(open_positions) == []


def test_over_threshold_returns_alert():
    monitor = ThematicMonitor(max_theme_pct=0.20, capital=100_000)
    open_positions = [
        {"ticker": "MU",   "shares": 100, "entry_price": 120.0},   # $12k NVDA chain
        {"ticker": "COHR", "shares": 100, "entry_price": 80.0},    # $8k NVDA chain = $20k = 20%
        {"ticker": "AMKR", "shares": 100, "entry_price": 30.0},    # $3k pushes to 23% > 20%
    ]
    alerts = monitor.check(open_positions)
    assert len(alerts) >= 1
    assert any("NVDA" in a for a in alerts)


def test_ticker_not_in_chain_ignored():
    monitor = ThematicMonitor(max_theme_pct=0.35, capital=100_000)
    assert monitor.check([{"ticker": "AAPL", "shares": 100, "entry_price": 200.0}]) == []
