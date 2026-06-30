from datetime import date
import time

import pandas as pd

from core.assets.bar import PriceSeries
from equities.data.prices import PriceFeed, YFinancePriceFeed


def _slow_download(**kwargs):
    time.sleep(5)
    return pd.DataFrame()


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

    def fake_download(**kwargs):
        assert kwargs["tickers"] == "ACME"
        assert kwargs["period"] == "5d"
        assert kwargs["interval"] == "1d"
        assert kwargs["timeout"] == 10
        return df

    monkeypatch.setattr("equities.data.prices.yf.download", fake_download)

    feed = YFinancePriceFeed(isolate_requests=False)
    ps = feed.history("ACME", period="5d", interval="1d")
    assert ps.ticker == "ACME"
    assert ps.closes == [10.5, 11.0]
    assert ps.bars[0].day == date(2026, 1, 2)
    assert ps.bars[1].volume == 1200


def test_yfinance_feed_empty_df_returns_empty_series(monkeypatch):
    monkeypatch.setattr("equities.data.prices.yf.download", lambda **kwargs: pd.DataFrame())
    ps = YFinancePriceFeed(isolate_requests=False).history("BADTICKER")
    assert ps.bars == []


def test_yfinance_feed_exception_returns_empty_series(monkeypatch):
    def fake_download(**kwargs):
        raise RuntimeError("network failed")

    monkeypatch.setattr("equities.data.prices.yf.download", fake_download)
    ps = YFinancePriceFeed(retries=0, isolate_requests=False).history("BADTICKER")
    assert ps.bars == []


def test_yfinance_feed_passes_timeout_when_supported(monkeypatch):
    seen = {}

    def fake_download(**kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return pd.DataFrame()

    monkeypatch.setattr("equities.data.prices.yf.download", fake_download)
    YFinancePriceFeed(timeout=7, isolate_requests=False).history("ACME")
    assert seen["timeout"] == 7


def test_yfinance_feed_handles_nan_volume(monkeypatch):
    """Test that NaN Volume values are coerced to 0 without crashing."""
    df = pd.DataFrame(
        {
            "Open": [10.0, 10.5],
            "High": [11.0, 12.0],
            "Low": [9.5, 10.0],
            "Close": [10.5, 11.0],
            "Volume": [1000, float("nan")],  # Second volume is NaN
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    def fake_download(**kwargs):
        return df

    monkeypatch.setattr("equities.data.prices.yf.download", fake_download)

    feed = YFinancePriceFeed(isolate_requests=False)
    ps = feed.history("ACME")
    assert len(ps.bars) == 2
    assert ps.bars[0].volume == 1000
    assert ps.bars[1].volume == 0  # NaN coerced to 0


def test_yfinance_feed_hard_timeout_terminates_blocked_download():
    started = time.monotonic()
    feed = YFinancePriceFeed(
        timeout=0.05,
        retries=0,
        download=_slow_download,
    )

    ps = feed.history("STUCK")

    assert time.monotonic() - started < 1
    assert ps.bars == []
    assert feed.failure_reason("STUCK") == "timeout after 0.05s"
