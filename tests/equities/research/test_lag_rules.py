from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.assets.bar import Bar, PriceSeries
from equities.research.lag_rules import (
    above_smas,
    atr,
    bar_on_or_before,
    discovery_lag_pct,
    is_chased,
    makes_period_high,
    opportunity_score,
    return_pct,
    sma,
    stop_from_atr,
)


def _series(ticker: str, closes: list[float]) -> PriceSeries:
    start = date(2025, 1, 1)
    bars = [
        Bar(
            day=start + timedelta(days=idx),
            open=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1_000_000,
        )
        for idx, close in enumerate(closes)
    ]
    return PriceSeries(ticker=ticker, bars=bars)


def _bars(ticker: str, rows: list[tuple[float, float, float, float]]) -> PriceSeries:
    start = date(2025, 1, 1)
    return PriceSeries(
        ticker=ticker,
        bars=[
            Bar(
                day=start + timedelta(days=idx),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1_000_000,
            )
            for idx, (open_, high, low, close) in enumerate(rows)
        ],
    )


def test_opportunity_score_formula():
    assert opportunity_score(lag_1y=60.0, lag_3mo=25.0, lag_1mo=10.0, bottleneck=0.55) == pytest.approx(0.1843)


def test_discovery_lag_threshold_inputs():
    trunk = _series("NVDA", [100.0] * 8 + [180.0] * 252)
    leaf = _series("AMAT", [100.0] * 8 + [120.0] * 252)

    assert discovery_lag_pct(trunk, leaf, 252) == pytest.approx(60.0)


def test_chase_rejection():
    calm = _series("CALM", [100.0] * 255 + [101.0, 102.0, 103.0, 104.0, 105.0])
    chased = _series("RUN", [100.0] * 255 + [120.0, 125.0, 130.0, 135.0, 140.0])

    assert is_chased(calm) is False
    assert is_chased(chased) is True


def test_sma_and_atr_with_stub_bars():
    series = _series("TREND", [float(100 + idx) for idx in range(220)])

    assert return_pct(series, 20) > 0
    assert sma(series, 20) == pytest.approx(309.5)
    assert above_smas(series, (50, 200)) is True
    assert atr(series, 20) == pytest.approx(2.0)


def test_bar_on_or_before_boundaries():
    series = _series("DAY", [100.0, 101.0, 102.0])

    assert bar_on_or_before(series, date(2025, 1, 2)) == 1
    assert bar_on_or_before(series, date(2024, 12, 31)) is None
    assert bar_on_or_before(series, date(2025, 1, 10)) == 2


def test_end_index_ignores_future_bars():
    series = _series("FUTURE", [100.0] * 220 + [160.0] * 5)

    assert return_pct(series, 5, end_index=219) == pytest.approx(0.0)
    assert is_chased(series, end_index=219) is False
    assert is_chased(series) is True
    assert makes_period_high(series, 20, end_index=219) is True
    assert above_smas(series, (20,), end_index=219) is False


def test_stop_from_atr_uses_requested_end_index():
    calm_then_wild = _bars(
        "ATR",
        [(100.0, 101.0, 99.0, 100.0)] * 25 + [(100.0, 140.0, 60.0, 100.0)] * 5,
    )

    assert stop_from_atr(100.0, calm_then_wild, end_index=24) == pytest.approx(97.0)
