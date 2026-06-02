"""07b — Quality screener for the DCA core sleeve.

Screens large-cap instruments for accumulation candidates based on:
- Gross margins ≥ min_gross_margins (default 35%)
- Trailing PE ≤ max_trailing_pe (default 30x) OR no PE but positive revenue growth
- Market cap ≥ min_cap_m (default $5B, i.e. large-cap)
- Revenue growth ≥ min_revenue_growth (default -0.05, allowing slight contraction)

The Core sleeve does NOT require a catalyst event — it is systematic DCA accumulation
into quality businesses at reasonable prices.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.assets.instrument import CapTier, Instrument
from equities.data.fundamentals import FundamentalsSnapshot


class FundamentalsProvider(Protocol):
    def fetch(self, ticker: str) -> FundamentalsSnapshot: ...


@dataclass(frozen=True)
class QualityCandidate:
    instrument: Instrument
    score: float       # 0.0–1.0
    evidence: str      # human-readable summary of why it passed


class QualityScreen:
    """Rank large-cap instruments by fundamental quality for DCA accumulation.

    Args:
        fundamentals:         Provider of fundamental snapshots.
        min_gross_margins:    Minimum gross margin ratio (default 0.35).
        max_trailing_pe:      Maximum trailing P/E (default 30.0). Instruments
                              with no PE are allowed if revenue growth ≥ 0.
        min_cap_m:            Minimum market cap in $M (default 5_000 = $5B).
        min_revenue_growth:   Minimum YoY revenue growth (default -0.05).
    """

    def __init__(
        self,
        fundamentals: FundamentalsProvider,
        min_gross_margins: float = 0.35,
        max_trailing_pe: float = 45.0,
        min_cap_m: float = 5_000.0,
        min_revenue_growth: float = -0.05,
    ) -> None:
        self._fundamentals = fundamentals
        self._min_gm = min_gross_margins
        self._max_pe = max_trailing_pe
        self._min_cap = min_cap_m
        self._min_rev_growth = min_revenue_growth

    def scan(self, universe: list[Instrument]) -> list[QualityCandidate]:
        """Return quality-ranked large-cap candidates. Sorted by score descending."""
        results: list[QualityCandidate] = []

        for inst in universe:
            if inst.cap_tier != CapTier.LARGE:
                continue

            snap = self._fundamentals.fetch(inst.ticker)
            candidate = self._evaluate(inst, snap)
            if candidate is not None:
                results.append(candidate)

        results.sort(key=lambda c: c.score, reverse=True)
        return results

    # ------------------------------------------------------------------

    def _evaluate(
        self, inst: Instrument, snap: FundamentalsSnapshot
    ) -> QualityCandidate | None:
        reasons: list[str] = []
        score = 0.0

        # --- Market cap gate (hard filter) ---
        cap = snap.market_cap_m
        if cap is not None and cap < self._min_cap:
            return None

        # --- Gross margins ---
        gm = snap.gross_margins
        if gm is None:
            return None  # can't assess quality without margins
        if gm < self._min_gm:
            return None
        # Score 0–0.4 based on margins (0.35 → 0, 0.70+ → 0.4)
        score += min(0.4, (gm - self._min_gm) / 0.35 * 0.4)
        reasons.append(f"gross_margins={gm:.0%}")

        # --- Trailing PE ---
        pe = snap.trailing_pe
        rev_g = snap.revenue_growth or 0.0
        if pe is not None:
            if pe > self._max_pe:
                return None
            # Score 0–0.3 (lower PE = higher score)
            pe_score = max(0.0, 1.0 - pe / self._max_pe) * 0.3
            score += pe_score
            reasons.append(f"trailing_pe={pe:.1f}")
        else:
            # No PE (unprofitable or N/A) — allow if growing
            if rev_g < 0:
                return None
            reasons.append("no_pe (growing)")

        # --- Revenue growth ---
        if rev_g < self._min_rev_growth:
            return None
        # Score 0–0.3 based on growth (0% → 0, 30%+ → 0.3)
        score += min(0.3, max(0.0, rev_g) / 0.30 * 0.3)
        reasons.append(f"rev_growth={rev_g:+.0%}")

        evidence = "  |  ".join(reasons)
        return QualityCandidate(
            instrument=inst,
            score=round(score, 4),
            evidence=evidence,
        )
