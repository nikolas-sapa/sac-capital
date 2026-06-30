from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.assets.bar import Bar, PriceSeries
from equities.research.lag_rules import (
    above_smas,
    atr,
    discovery_lag_pct,
    is_chased,
    opportunity_score,
    return_pct,
    sma,
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
