from datetime import date

import pandas as pd

from core.assets.bar import PriceSeries
from equities.data.prices import PriceFeed, YFinancePriceFeed


def test_pricefeed_protocol_runtime_checkable():
    class FakeFeed:
        def history(self, ticker, period="1y", interval="1d"):
            return PriceSeries(ticker=ticker, bars=[])
    assert isinstance(FakeFeed(), PriceFeed)


def test_yfinance_feed_maps_dataframe_to_priceseries(monkeypatch):
    df = pd.DataFrame(
        {
            "Open": [10.0, 10.5],
            "High": [11.0, 12.0],
            "Low": [9.5, 10.0],
            "Close": [10.5, 11.0],
            "Volume": [1000, 1200],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
        def history(self, period, interval):
            return df

    monkeypatch.setattr("equities.data.prices.yf.Ticker", FakeTicker)

    feed = YFinancePriceFeed()
    ps = feed.history("ACME", period="5d", interval="1d")
    assert ps.ticker == "ACME"
    assert ps.closes == [10.5, 11.0]
    assert ps.bars[0].day == date(2026, 1, 2)
    assert ps.bars[1].volume == 1200


def test_yfinance_feed_empty_df_returns_empty_series(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            pass
        def history(self, period, interval):
            return pd.DataFrame()
    monkeypatch.setattr("equities.data.prices.yf.Ticker", FakeTicker)
    ps = YFinancePriceFeed().history("BADTICKER")
    assert ps.bars == []


def test_yfinance_feed_exception_returns_empty_series(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            pass
        def history(self, period, interval, timeout=None):
            raise RuntimeError("network failed")
    monkeypatch.setattr("equities.data.prices.yf.Ticker", FakeTicker)
    ps = YFinancePriceFeed(retries=0).history("BADTICKER")
    assert ps.bars == []


def test_yfinance_feed_passes_timeout_when_supported(monkeypatch):
    seen = {}

    class FakeTicker:
        def __init__(self, symbol):
            pass
        def history(self, period, interval, timeout=None):
            seen["timeout"] = timeout
            return pd.DataFrame()
    monkeypatch.setattr("equities.data.prices.yf.Ticker", FakeTicker)
    YFinancePriceFeed(timeout=7).history("ACME")
    assert seen["timeout"] == 7
