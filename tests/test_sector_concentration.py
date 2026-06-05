"""Tests for sector concentration fuse in RiskKernel."""
from __future__ import annotations

from core.assets.instrument import CapTier, Instrument
from equities.risk.kernel import RiskKernel
from equities.strategy import Recommendation, Sleeve


def _rec(ticker: str, entry: float = 100.0) -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.MID),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=entry * 0.92,
        take_profit=entry * 1.20,
        size_pct=0.02,
        confidence=0.70,
        catalyst="test",
        thesis="test",
        horizon="2w",
    )


def test_sector_concentration_blocks_entry():
    kernel = RiskKernel(capital=100_000, max_positions=10, max_sector_pct=0.25)
    open_positions = [
        {"ticker": "KLIC", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "ONTO", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "AMKR", "sleeve": "swing", "shares": 50,  "entry_price": 100.0, "sector": "Semiconductors"},
    ]
    # Existing semiconductors = $25k = 25% — adding one more would push over
    result = kernel.approve(
        _rec("LRCX"),
        open_positions,
        sector_lookup={"LRCX": "Semiconductors"},
    )
    assert not result.approved
    assert "sector_concentration" in result.rejection_reason


def test_different_sector_not_blocked():
    kernel = RiskKernel(capital=100_000, max_positions=10, max_sector_pct=0.25)
    open_positions = [
        {"ticker": "KLIC", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "ONTO", "sleeve": "swing", "shares": 100, "entry_price": 100.0, "sector": "Semiconductors"},
        {"ticker": "AMKR", "sleeve": "swing", "shares": 50,  "entry_price": 100.0, "sector": "Semiconductors"},
    ]
    result = kernel.approve(
        _rec("CRWD"),
        open_positions,
        sector_lookup={"CRWD": "Technology"},
    )
    assert result.approved
