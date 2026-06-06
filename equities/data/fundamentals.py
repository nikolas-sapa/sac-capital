from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class FundamentalsSnapshot:
    """Key fundamental metrics for a single ticker, fetched at a point in time."""

    ticker: str
    market_cap_m: float | None    # market cap in $M
    trailing_pe: float | None
    forward_pe: float | None
    gross_margins: float | None   # 0.0–1.0
    revenue_growth: float | None  # YoY, e.g. 0.20 = +20%
    sector: str
    analyst_count: int            # number of sell-side analysts covering
    # Enriched fields
    eps_trend: list[float] | None = None       # last 4 quarterly EPS, oldest first
    short_interest_pct: float | None = None    # short interest as % of float
    peg_ratio: float | None = None
    operating_margins: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow_m: float | None = None      # free cash flow in $M

    def __post_init__(self) -> None:
        if self.eps_trend is None:
            self.eps_trend = []


@runtime_checkable
class FundamentalsProvider(Protocol):
    def fetch(self, ticker: str) -> FundamentalsSnapshot: ...


class YFinanceFundamentals:
    """Fetch fundamental metrics from yfinance (free, delayed)."""

    def fetch(self, ticker: str) -> FundamentalsSnapshot:
        import yfinance as yf

        t = yf.Ticker(ticker)
        try:
            info = t.info
        except Exception:
            return FundamentalsSnapshot(
                ticker=ticker,
                market_cap_m=None,
                trailing_pe=None,
                forward_pe=None,
                gross_margins=None,
                revenue_growth=None,
                sector="",
                analyst_count=0,
            )
        cap_raw = info.get("marketCap")
        fcf_raw = info.get("freeCashflow")

        eps_trend: list[float] = []
        try:
            eh = t.earnings_history
            if eh is not None and not eh.empty and "epsActual" in eh.columns:
                recent = eh.sort_index().tail(4)
                eps_trend = [float(v) for v in recent["epsActual"].fillna(0).tolist()]
        except Exception:
            eps_trend = []

        return FundamentalsSnapshot(
            ticker=ticker,
            market_cap_m=cap_raw / 1e6 if cap_raw else None,
            trailing_pe=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            gross_margins=info.get("grossMargins"),
            revenue_growth=info.get("revenueGrowth"),
            sector=info.get("sector", ""),
            analyst_count=info.get("numberOfAnalystOpinions", 0) or 0,
            eps_trend=eps_trend,
            short_interest_pct=info.get("shortPercentOfFloat"),
            peg_ratio=info.get("pegRatio"),
            operating_margins=info.get("operatingMargins"),
            debt_to_equity=info.get("debtToEquity"),
            free_cash_flow_m=fcf_raw / 1e6 if fcf_raw else None,
        )
