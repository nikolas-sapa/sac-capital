"""Tests for enriched FundamentalsSnapshot fields."""
from __future__ import annotations

from equities.data.fundamentals import FundamentalsSnapshot


def test_snapshot_has_enriched_fields():
    snap = FundamentalsSnapshot(
        ticker="AMD",
        market_cap_m=250_000.0,
        trailing_pe=35.0,
        forward_pe=28.0,
        gross_margins=0.53,
        revenue_growth=0.17,
        sector="Semiconductors",
        analyst_count=42,
        eps_trend=[-0.40, -0.25, -0.10, 0.05],
        short_interest_pct=1.8,
        peg_ratio=1.4,
        operating_margins=0.22,
        debt_to_equity=0.35,
        free_cash_flow_m=1_200.0,
    )
    assert snap.eps_trend == [-0.40, -0.25, -0.10, 0.05]
    assert snap.short_interest_pct == 1.8
    assert snap.peg_ratio == 1.4
    assert snap.operating_margins == 0.22


def test_enriched_fields_default_safely():
    snap = FundamentalsSnapshot(
        ticker="TEST",
        market_cap_m=None,
        trailing_pe=None,
        forward_pe=None,
        gross_margins=None,
        revenue_growth=None,
        sector="",
        analyst_count=0,
    )
    assert snap.eps_trend == []
    assert snap.short_interest_pct is None
    assert snap.peg_ratio is None
