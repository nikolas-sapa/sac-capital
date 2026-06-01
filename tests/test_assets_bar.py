from datetime import date

from core.assets.bar import Bar, PriceSeries


def test_bar_holds_ohlcv():
    b = Bar(day=date(2026, 1, 2), open=10.0, high=11.0, low=9.5, close=10.5, volume=1000)
    assert b.close == 10.5
    assert b.volume == 1000


def test_priceseries_closes_in_order():
    bars = [
        Bar(day=date(2026, 1, 2), open=10, high=11, low=9, close=10.5, volume=100),
        Bar(day=date(2026, 1, 3), open=10.5, high=12, low=10, close=11.0, volume=120),
    ]
    ps = PriceSeries(ticker="ACME", bars=bars)
    assert ps.closes == [10.5, 11.0]
    assert ps.latest.close == 11.0


def test_priceseries_latest_none_when_empty():
    ps = PriceSeries(ticker="ACME", bars=[])
    assert ps.latest is None
