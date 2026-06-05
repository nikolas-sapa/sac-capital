"""Tests for InflectionScanner."""
from __future__ import annotations

from core.assets.instrument import CapTier, Instrument
from equities.data.fundamentals import FundamentalsSnapshot
from equities.screen.inflection_screen import InflectionCandidate, InflectionScanner


def _inst(ticker: str) -> Instrument:
    return Instrument(ticker, ticker, "NASDAQ", CapTier.MID)


def _snap(ticker: str, eps: list[float], rev: float = 0.30) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        ticker=ticker,
        market_cap_m=2_000.0,
        trailing_pe=None,
        forward_pe=None,
        gross_margins=0.60,
        revenue_growth=rev,
        sector="Technology",
        analyst_count=6,
        eps_trend=eps,
        short_interest_pct=12.0,
    )


class _StubFundamentals:
    def __init__(self, snaps: dict) -> None:
        self._snaps = snaps

    def fetch(self, ticker: str) -> FundamentalsSnapshot:
        return self._snaps[ticker]


def test_improving_eps_near_zero_is_flagged():
    scanner = InflectionScanner(_StubFundamentals({"AFRM": _snap("AFRM", [-0.45, -0.30, -0.15, -0.05])}))
    results = scanner.scan([_inst("AFRM")])
    assert len(results) == 1
    assert results[0].ticker == "AFRM"
    assert results[0].quarters_to_profit <= 2


def test_already_profitable_not_flagged():
    scanner = InflectionScanner(_StubFundamentals({"META": _snap("META", [1.0, 1.5, 2.0, 2.5])}))
    assert scanner.scan([_inst("META")]) == []


def test_deteriorating_eps_not_flagged():
    scanner = InflectionScanner(_StubFundamentals({"PTON": _snap("PTON", [-0.05, -0.15, -0.30, -0.50])}))
    assert scanner.scan([_inst("PTON")]) == []


def test_no_eps_data_skipped():
    scanner = InflectionScanner(_StubFundamentals({"X": _snap("X", [])}))
    assert scanner.scan([_inst("X")]) == []
