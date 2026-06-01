from __future__ import annotations

from typing import Protocol, runtime_checkable

import yfinance as yf

from core.assets.bar import Bar, PriceSeries


@runtime_checkable
class PriceFeed(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


class YFinancePriceFeed:
    """Daily OHLCV via yfinance. auto_adjust=True (default) so Close is split/dividend adjusted."""

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        bars: list[Bar] = []
        for ts, r in df.iterrows():
            bars.append(
                Bar(
                    day=ts.date(),
                    open=float(r["Open"]),
                    high=float(r["High"]),
                    low=float(r["Low"]),
                    close=float(r["Close"]),
                    volume=int(r["Volume"]),
                )
            )
        return PriceSeries(ticker=ticker, bars=bars)
