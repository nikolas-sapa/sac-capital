from __future__ import annotations

import math
import time
from typing import Protocol, runtime_checkable

import yfinance as yf
import pandas as pd

from core.assets.bar import Bar, PriceSeries
from equities.data.yfinance_utils import call_quietly


@runtime_checkable
class PriceFeed(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


class YFinancePriceFeed:
    """Daily OHLCV via yfinance downloads.

    `yf.download()` avoids the per-ticker consent flow that `Ticker.history()`
    can trigger on Yahoo-hosted endpoints, while still returning adjusted bars
    when `auto_adjust=True`.
    """

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
                        lambda: yf.download(
                            tickers=ticker,
                            period=period,
                            interval=interval,
                            progress=False,
                            auto_adjust=True,
                            threads=False,
                            timeout=self._timeout,
                        )
                    )
                except TypeError:
                    df = call_quietly(
                        lambda: yf.download(
                            tickers=ticker,
                            period=period,
                            interval=interval,
                            progress=False,
                            auto_adjust=True,
                            threads=False,
                        )
                    )
                duration = time.monotonic() - started
                print(
                    f"  [PROVIDER] source=yfinance_download ticker={ticker} "
                    f"attempt={attempt + 1} ok duration_s={duration:.2f}"
                )
                break
            except Exception as exc:
                duration = time.monotonic() - started
                print(
                    f"  [PROVIDER] source=yfinance_download ticker={ticker} "
                    f"attempt={attempt + 1} error={exc} duration_s={duration:.2f}"
                )
        if df is None:
            return PriceSeries(ticker=ticker, bars=[])

        if isinstance(df, pd.DataFrame) and df.empty:
            return PriceSeries(ticker=ticker, bars=[])

        if isinstance(df, pd.DataFrame) and isinstance(df.columns, pd.MultiIndex):
            df = df.xs(ticker, axis=1, level=1, drop_level=True)

        bars: list[Bar] = []
        for ts, r in df.iterrows():
            close = float(r["Close"])
            if math.isnan(close):  # skip incomplete intraday bars
                continue
            volume_raw = r["Volume"]
            volume = 0 if (isinstance(volume_raw, float) and math.isnan(volume_raw)) else int(volume_raw)
            bars.append(
                Bar(
                    day=ts.date(),
                    open=float(r["Open"]),
                    high=float(r["High"]),
                    low=float(r["Low"]),
                    close=close,
                    volume=volume,
                )
            )
        return PriceSeries(ticker=ticker, bars=bars)
