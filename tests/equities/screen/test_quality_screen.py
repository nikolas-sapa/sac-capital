"""Tests for the DCA core quality screener (07b)."""
import pytest

from core.assets.instrument import CapTier, Instrument
from equities.data.fundamentals import FundamentalsSnapshot
from equities.screen.quality_screen import QualityCandidate, QualityScreen


def _inst(ticker: str, cap: CapTier = CapTier.LARGE) -> Instrument:
    return Instrument(ticker=ticker, name=ticker, exchange="NYSE", cap_tier=cap)


def _snap(
    ticker: str,
    cap_m: float = 10_000.0,
    gm: float = 0.50,
    pe: float = 20.0,
    rev_g: float = 0.10,
    sector: str = "Technology",
) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        ticker=ticker,
        market_cap_m=cap_m,
        trailing_pe=pe,
        forward_pe=None,
        gross_margins=gm,
        revenue_growth=rev_g,
        sector=sector,
        analyst_count=10,
    )


class FakeFundamentals:
    def __init__(self, snaps: dict[str, FundamentalsSnapshot]):
        self._snaps = snaps

    def fetch(self, ticker: str) -> FundamentalsSnapshot:
        return self._snaps[ticker]


class FailingFundamentals:
    def fetch(self, ticker: str) -> FundamentalsSnapshot:
        raise RuntimeError("provider failed")


def test_high_quality_passes():
    inst = _inst("MSFT")
    screen = QualityScreen(FakeFundamentals({"MSFT": _snap("MSFT")}))
    results = screen.scan([inst])
    assert len(results) == 1
    assert results[0].instrument == inst


def test_low_gross_margins_rejected():
    inst = _inst("X")
    snap = _snap("X", gm=0.20)
    screen = QualityScreen(FakeFundamentals({"X": snap}))
    assert screen.scan([inst]) == []


def test_high_pe_rejected():
    inst = _inst("Y")
    snap = _snap("Y", pe=50.0)
    screen = QualityScreen(FakeFundamentals({"Y": snap}))
    assert screen.scan([inst]) == []


def test_negative_revenue_growth_rejected():
    inst = _inst("Z")
    snap = _snap("Z", rev_g=-0.20)
    screen = QualityScreen(FakeFundamentals({"Z": snap}))
    assert screen.scan([inst]) == []


def test_no_pe_but_positive_growth_passes():
    inst = _inst("BIOPHARMA")
    snap = FundamentalsSnapshot(
        ticker="BIOPHARMA", market_cap_m=8_000.0, trailing_pe=None, forward_pe=None,
        gross_margins=0.80, revenue_growth=0.25, sector="Healthcare", analyst_count=5,
    )
    screen = QualityScreen(FakeFundamentals({"BIOPHARMA": snap}))
    results = screen.scan([inst])
    assert len(results) == 1


def test_no_pe_and_negative_growth_rejected():
    inst = _inst("LOSER")
    snap = FundamentalsSnapshot(
        ticker="LOSER", market_cap_m=8_000.0, trailing_pe=None, forward_pe=None,
        gross_margins=0.60, revenue_growth=-0.10, sector="Retail", analyst_count=2,
    )
    screen = QualityScreen(FakeFundamentals({"LOSER": snap}))
    assert screen.scan([inst]) == []


def test_small_cap_excluded():
    inst = _inst("MICRO", cap=CapTier.SMALL)
    screen = QualityScreen(FakeFundamentals({"MICRO": _snap("MICRO")}))
    assert screen.scan([inst]) == []


def test_mid_cap_excluded():
    inst = _inst("MID", cap=CapTier.MID)
    screen = QualityScreen(FakeFundamentals({"MID": _snap("MID")}))
    assert screen.scan([inst]) == []


def test_results_sorted_by_score_descending():
    insts = [_inst("A"), _inst("B"), _inst("C")]
    snaps = {
        "A": _snap("A", gm=0.40, pe=28.0, rev_g=0.05),   # lower score
        "B": _snap("B", gm=0.70, pe=15.0, rev_g=0.25),   # high score
        "C": _snap("C", gm=0.55, pe=20.0, rev_g=0.12),   # medium
    }
    screen = QualityScreen(FakeFundamentals(snaps))
    results = screen.scan(insts)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].instrument.ticker == "B"


def test_evidence_contains_key_metrics():
    inst = _inst("META")
    screen = QualityScreen(FakeFundamentals({"META": _snap("META", gm=0.80, pe=22.0, rev_g=0.15)}))
    result = screen.scan([inst])[0]
    assert "gross_margins" in result.evidence
    assert "trailing_pe" in result.evidence
    assert "rev_growth" in result.evidence


def test_no_gross_margins_data_rejected():
    inst = _inst("MYSTERY")
    snap = FundamentalsSnapshot(
        ticker="MYSTERY", market_cap_m=10_000.0, trailing_pe=15.0, forward_pe=None,
        gross_margins=None, revenue_growth=0.10, sector="Unknown", analyst_count=0,
    )
    screen = QualityScreen(FakeFundamentals({"MYSTERY": snap}))
    assert screen.scan([inst]) == []


def test_provider_failure_skips_ticker():
    inst = _inst("STALE")
    screen = QualityScreen(FailingFundamentals())
    assert screen.scan([inst]) == []
