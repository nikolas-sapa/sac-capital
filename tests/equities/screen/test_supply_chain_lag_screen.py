from __future__ import annotations

from datetime import date, timedelta

from core.assets.bar import Bar, PriceSeries
from equities.screen.supply_chain_lag_screen import (
    STRATEGY_MULTI_TRUNK,
    STRATEGY_POST_BREAKOUT,
    STRATEGY_SEMI_BOTTLENECK,
    SupplyChainLagScreen,
)


class FakePriceFeed:
    def __init__(self, series: dict[str, PriceSeries]) -> None:
        self._series = series

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        return self._series.get(ticker, _flat_series(ticker))


def _series_from_points(ticker: str, points: dict[int, float], length: int = 260) -> PriceSeries:
    closes = [0.0 for _ in range(length)]
    ordered = sorted({0: points.get(0, 100.0), length - 1: points.get(length - 1, 100.0), **points}.items())
    for (start_idx, start_value), (end_idx, end_value) in zip(ordered, ordered[1:]):
        span = end_idx - start_idx
        for idx in range(start_idx, end_idx + 1):
            weight = 0.0 if span == 0 else (idx - start_idx) / span
            closes[idx] = start_value + (end_value - start_value) * weight
    return _series(ticker, closes)


def _series(ticker: str, closes: list[float]) -> PriceSeries:
    start = date(2025, 1, 1)
    bars = [
        Bar(
            day=start + timedelta(days=idx),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=5_000_000,
        )
        for idx, close in enumerate(closes)
    ]
    return PriceSeries(ticker=ticker, bars=bars)


def _flat_series(ticker: str) -> PriceSeries:
    return _series(ticker, [100.0 for _ in range(260)])


def test_semi_bottleneck_candidate_emitted_for_amat_style_setup():
    feed = FakePriceFeed({
        "AMD": _series_from_points("AMD", {7: 100.0, 196: 150.0, 238: 170.0, 259: 200.0}),
        "AMAT": _series_from_points("AMAT", {7: 100.0, 196: 115.0, 238: 120.0, 259: 120.0}),
    })

    candidates = SupplyChainLagScreen(feed).scan_semi_bottleneck()

    amat = [c for c in candidates if c.ticker == "AMAT" and c.trunk == "AMD"]
    assert len(amat) == 1
    assert amat[0].strategy == STRATEGY_SEMI_BOTTLENECK
    assert amat[0].features["lag_1y"] >= 25.0
    assert amat[0].features["opportunity_score"] >= 0.18


def test_multi_trunk_candidate_requires_two_active_trunks():
    active_feed = FakePriceFeed({
        "QQQ": _flat_series("QQQ"),
        "NVDA": _series_from_points("NVDA", {196: 100.0, 259: 130.0}),
        "AMD": _series_from_points("AMD", {196: 100.0, 259: 125.0}),
        "COHR": _series_from_points("COHR", {196: 100.0, 238: 102.0, 259: 105.0}),
    })
    inactive_feed = FakePriceFeed({
        "QQQ": _flat_series("QQQ"),
        "NVDA": _series_from_points("NVDA", {196: 100.0, 259: 130.0}),
        "AMD": _flat_series("AMD"),
        "COHR": _series_from_points("COHR", {196: 100.0, 238: 102.0, 259: 105.0}),
    })

    active = SupplyChainLagScreen(active_feed).scan_multi_trunk()
    inactive = SupplyChainLagScreen(inactive_feed).scan_multi_trunk()

    assert any(c.ticker == "COHR" and c.strategy == STRATEGY_MULTI_TRUNK for c in active)
    assert not any(c.ticker == "COHR" for c in inactive)


def test_breakout_strategy_sets_delay_and_rejects_chased_leaf():
    trunk = _series_from_points("NVDA", {196: 90.0, 238: 100.0, 259: 125.0})
    leaf = _series_from_points("MU", {0: 50.0, 196: 90.0, 238: 100.0, 256: 104.0, 259: 105.0})
    chased_leaf = _series_from_points("MU", {0: 50.0, 196: 90.0, 238: 100.0, 256: 100.0, 259: 112.0})

    accepted = SupplyChainLagScreen(FakePriceFeed({"NVDA": trunk, "MU": leaf})).scan_post_breakout()
    rejected = SupplyChainLagScreen(FakePriceFeed({"NVDA": trunk, "MU": chased_leaf})).scan_post_breakout()

    mu = [c for c in accepted if c.ticker == "MU" and c.trunk == "NVDA"]
    assert len(mu) == 1
    assert mu[0].strategy == STRATEGY_POST_BREAKOUT
    assert mu[0].features["entry_delay_days"] == 3
    assert not any(c.ticker == "MU" and c.trunk == "NVDA" for c in rejected)
