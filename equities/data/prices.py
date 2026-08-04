from __future__ import annotations

import math
import time
from typing import Any, Callable, Protocol, runtime_checkable

import yfinance as yf
import pandas as pd

from core.assets.bar import Bar, PriceSeries
from equities.data.yfinance_utils import call_quietly, IsolatedCall


def _download_request(download: Callable[..., Any], kwargs: dict[str, Any]):
    try:
        return call_quietly(lambda: download(**kwargs))
    except TypeError:
        kwargs.pop("timeout", None)
        return call_quietly(lambda: download(**kwargs))


@runtime_checkable
class PriceFeed(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


class YFinancePriceFeed:
    """Daily OHLCV via yfinance downloads.

    `yf.download()` avoids the per-ticker consent flow that `Ticker.history()`
    can trigger on Yahoo-hosted endpoints, while still returning adjusted bars
    when `auto_adjust=True`.
    """

    def __init__(
        self,
        timeout: float = 10,
        retries: int = 1,
        *,
        download: Callable[..., Any] | None = None,
        isolate_requests: bool = True,
    ) -> None:
        self._timeout = timeout
        self._retries = retries
        self._download = download or yf.download
        self._isolate_requests = isolate_requests
        self._failures: dict[str, str] = {}
        self._isolated_download = IsolatedCall(_download_request, timeout) if isolate_requests else None

    def failure_reason(self, ticker: str) -> str | None:
        return self._failures.get(ticker)

    def _download_once(self, kwargs: dict[str, Any]):
        if not self._isolate_requests:
            try:
                return call_quietly(lambda: self._download(**kwargs))
            except TypeError:
                kwargs.pop("timeout", None)
                return call_quietly(lambda: self._download(**kwargs))

        return self._isolated_download(
            self._download,
            kwargs,
        )

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        df = None
        self._failures.pop(ticker, None)
        for attempt in range(self._retries + 1):
            started = time.monotonic()
            try:
                df = self._download_once({
                    "tickers": ticker,
                    "period": period,
                    "interval": interval,
                    "progress": False,
                    "auto_adjust": True,
                    "threads": False,
                    "timeout": self._timeout,
                })
                duration = time.monotonic() - started
                # An empty frame is a failure, not a success. Reporting it as
                # "ok" made a rate-limited run look healthy while every
                # downstream technical gate silently lost its input.
                if isinstance(df, pd.DataFrame) and df.empty:
                    self._failures[ticker] = "empty_frame"
                    print(
                        f"  [PROVIDER] source=yfinance_download ticker={ticker} "
                        f"attempt={attempt + 1} error=empty_frame duration_s={duration:.2f}"
                    )
                    df = None
                    continue
                print(
                    f"  [PROVIDER] source=yfinance_download ticker={ticker} "
                    f"attempt={attempt + 1} ok duration_s={duration:.2f}"
                )
                break
            except Exception as exc:
                self._failures[ticker] = str(exc)
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
