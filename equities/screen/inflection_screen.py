"""Inflection scanner — finds companies 1-2 quarters from first GAAP profitability."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.assets.instrument import Instrument
from equities.data.fundamentals import FundamentalsSnapshot


class FundamentalsProvider(Protocol):
    def fetch(self, ticker: str) -> FundamentalsSnapshot: ...


@dataclass(frozen=True)
class InflectionCandidate:
    ticker: str
    instrument: Instrument
    eps_trend: list[float]
    quarters_to_profit: int
    revenue_growth: float
    short_interest_pct: float | None
    evidence: str


class InflectionScanner:
    """Scan for companies approaching GAAP profitability.

    All must pass:
    - 3+ consecutive quarters of EPS improvement
    - Last quarter still negative
    - Last quarter EPS > max_eps_loss (close to zero)
    - Revenue growth >= min_revenue_growth
    """

    def __init__(
        self,
        fundamentals: FundamentalsProvider,
        max_eps_loss: float = -0.20,
        min_revenue_growth: float = 0.10,
    ) -> None:
        self._fundamentals = fundamentals
        self._max_eps_loss = max_eps_loss
        self._min_revenue_growth = min_revenue_growth

    def scan(self, universe: list[Instrument]) -> list[InflectionCandidate]:
        results: list[InflectionCandidate] = []
        for inst in universe:
            try:
                snap = self._fundamentals.fetch(inst.ticker)
            except Exception:
                continue
            c = self._evaluate(inst, snap)
            if c is not None:
                results.append(c)
        results.sort(key=lambda c: c.eps_trend[-1], reverse=True)
        return results

    def _evaluate(self, inst: Instrument, snap: FundamentalsSnapshot) -> InflectionCandidate | None:
        eps = snap.eps_trend or []
        if len(eps) < 3:
            return None
        if not all(eps[i] > eps[i - 1] for i in range(1, len(eps))):
            return None
        last = eps[-1]
        if last >= 0:
            return None
        if last < self._max_eps_loss:
            return None
        rev_g = snap.revenue_growth or 0.0
        if rev_g < self._min_revenue_growth:
            return None
        avg_improvement = (eps[-1] - eps[0]) / (len(eps) - 1)
        quarters_to_profit = max(1, round(-last / avg_improvement)) if avg_improvement > 0 else 2
        si = snap.short_interest_pct
        evidence = (
            f"eps={[round(e, 2) for e in eps]} "
            f"rev={rev_g:+.0%}"
            + (f" si={si:.1f}%" if si else "")
        )
        return InflectionCandidate(
            ticker=inst.ticker,
            instrument=inst,
            eps_trend=eps,
            quarters_to_profit=min(quarters_to_profit, 2),
            revenue_growth=rev_g,
            short_interest_pct=si,
            evidence=evidence,
        )
