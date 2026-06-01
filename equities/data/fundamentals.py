from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
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


@runtime_checkable
class FundamentalsProvider(Protocol):
    def fetch(self, ticker: str) -> FundamentalsSnapshot: ...


class YFinanceFundamentals:
    """Fetch fundamental metrics from yfinance (free, delayed)."""

    def fetch(self, ticker: str) -> FundamentalsSnapshot:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        cap_raw = info.get("marketCap")
        return FundamentalsSnapshot(
            ticker=ticker,
            market_cap_m=cap_raw / 1e6 if cap_raw else None,
            trailing_pe=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            gross_margins=info.get("grossMargins"),
            revenue_growth=info.get("revenueGrowth"),
            sector=info.get("sector", ""),
            analyst_count=info.get("numberOfAnalystOpinions", 0) or 0,
        )
