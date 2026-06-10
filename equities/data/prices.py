from __future__ import annotations

import math
import time
from typing import Protocol, runtime_checkable

import yfinance as yf

from core.assets.bar import Bar, PriceSeries
from equities.data.yfinance_utils import call_quietly


@runtime_checkable
class PriceFeed(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


class YFinancePriceFeed:
    """Daily OHLCV via yfinance. auto_adjust=True (default) so Close is split/dividend adjusted."""

    def __init__(self, timeout: int = 10, retries: int = 1) -> None:
        self._timeout = timeout
        self._retries = retries

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        df = None
        for attempt in range(self._retries + 1):
            started = time.monotonic()
            try:
                try:
                    df = call_quietly(
                        lambda: yf.Ticker(ticker).history(
                            period=period,
                            interval=interval,
                            timeout=self._timeout,
                        )
                    )
                except TypeError:
                    df = call_quietly(
                        lambda: yf.Ticker(ticker).history(period=period, interval=interval)
                    )
                duration = time.monotonic() - started
                print(
                    f"  [PROVIDER] source=yfinance_history ticker={ticker} "
                    f"attempt={attempt + 1} ok duration_s={duration:.2f}"
                )
                break
            except Exception as exc:
                duration = time.monotonic() - started
                print(
                    f"  [PROVIDER] source=yfinance_history ticker={ticker} "
                    f"attempt={attempt + 1} error={exc} duration_s={duration:.2f}"
                )
        if df is None:
            return PriceSeries(ticker=ticker, bars=[])

        bars: list[Bar] = []
        for ts, r in df.iterrows():
            close = float(r["Close"])
            if math.isnan(close):  # skip incomplete intraday bars
                continue
            bars.append(
                Bar(
                    day=ts.date(),
                    open=float(r["Open"]),
                    high=float(r["High"]),
                    low=float(r["Low"]),
                    close=close,
                    volume=int(r["Volume"]),
                )
            )
        return PriceSeries(ticker=ticker, bars=bars)
