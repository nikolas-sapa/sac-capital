"""Deterministic rules for lagged supply-chain paper strategies."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

from core.assets.bar import PriceSeries
from equities.research.supply_chain import BottleneckScorer


@dataclass(frozen=True)
class LagFeatures:
    lag_1y: float
    lag_3mo: float
    lag_1mo: float
    bottleneck_score: float
    opportunity_score: float


def return_pct(series: PriceSeries, days: int, *, end_index: int | None = None) -> float | None:
    """Return percent move over N bars ending at end_index."""
    closes = series.closes
    if not closes:
        return None
    end = len(closes) - 1 if end_index is None else end_index
    start = end - days
    if start < 0 or end >= len(closes):
        return None
    start_price = closes[start]
    end_price = closes[end]
    if start_price <= 0:
        return None
    return (end_price / start_price - 1.0) * 100.0


def discovery_lag_pct(
    trunk: PriceSeries,
    leaf: PriceSeries,
    days: int,
    *,
    trunk_end_index: int | None = None,
    leaf_end_index: int | None = None,
) -> float | None:
    trunk_return = return_pct(trunk, days, end_index=trunk_end_index)
    leaf_return = return_pct(leaf, days, end_index=leaf_end_index)
    if trunk_return is None or leaf_return is None:
        return None
    return trunk_return - leaf_return


def opportunity_score(*, lag_1y: float, lag_3mo: float, lag_1mo: float, bottleneck: float) -> float:
    positive_lag = (
        max(lag_1y, 0.0) * 0.35
        + max(lag_3mo, 0.0) * 0.40
        + max(lag_1mo, 0.0) * 0.25
    )
    return round((positive_lag / 100.0) * bottleneck, 4)


def lag_features(
    trunk_ticker: str,
    leaf_ticker: str,
    trunk: PriceSeries,
    leaf: PriceSeries,
    *,
    trunk_end_index: int | None = None,
    leaf_end_index: int | None = None,
) -> LagFeatures | None:
    lag_1y = discovery_lag_pct(trunk, leaf, 252, trunk_end_index=trunk_end_index, leaf_end_index=leaf_end_index)
    lag_3mo = discovery_lag_pct(trunk, leaf, 63, trunk_end_index=trunk_end_index, leaf_end_index=leaf_end_index)
    lag_1mo = discovery_lag_pct(trunk, leaf, 21, trunk_end_index=trunk_end_index, leaf_end_index=leaf_end_index)
    if lag_1y is None or lag_3mo is None or lag_1mo is None:
        return None
    bottleneck = BottleneckScorer().score(leaf_ticker, trunk_ticker)
    return LagFeatures(
        lag_1y=round(lag_1y, 4),
        lag_3mo=round(lag_3mo, 4),
        lag_1mo=round(lag_1mo, 4),
        bottleneck_score=bottleneck,
        opportunity_score=opportunity_score(
            lag_1y=lag_1y,
            lag_3mo=lag_3mo,
            lag_1mo=lag_1mo,
            bottleneck=bottleneck,
        ),
    )


def is_chased(
    series: PriceSeries,
    *,
    max_5d_return: float = 15.0,
    max_20d_return: float = 30.0,
    end_index: int | None = None,
) -> bool:
    ret_5 = return_pct(series, 5, end_index=end_index)
    ret_20 = return_pct(series, 20, end_index=end_index)
    return (ret_5 is not None and ret_5 > max_5d_return) or (
        ret_20 is not None and ret_20 > max_20d_return
    )


def sma(series: PriceSeries, window: int, *, end_index: int | None = None) -> float | None:
    closes = series.closes
    if not closes:
        return None
    end = len(closes) - 1 if end_index is None else end_index
    start = end - window + 1
    if start < 0 or end >= len(closes):
        return None
    return statistics.fmean(closes[start : end + 1])


def atr(series: PriceSeries, window: int = 20, *, end_index: int | None = None) -> float | None:
    bars = series.bars
    if not bars:
        return None
    end = len(bars) - 1 if end_index is None else end_index
    start = end - window + 1
    if start <= 0 or end >= len(bars):
        return None
    true_ranges: list[float] = []
    for idx in range(start, end + 1):
        bar = bars[idx]
        previous_close = bars[idx - 1].close
        true_ranges.append(max(
            bar.high - bar.low,
            abs(bar.high - previous_close),
            abs(bar.low - previous_close),
        ))
    return statistics.fmean(true_ranges)


def above_smas(series: PriceSeries, windows: tuple[int, ...], *, end_index: int | None = None) -> bool:
    if not series.bars:
        return False
    end = len(series.bars) - 1 if end_index is None else end_index
    if end < 0 or end >= len(series.bars):
        return False
    values = [sma(series, window, end_index=end) for window in windows]
    return all(value is not None and series.bars[end].close > value for value in values)


def makes_period_high(series: PriceSeries, days: int, *, end_index: int | None = None) -> bool:
    closes = series.closes
    if not closes:
        return False
    end = len(closes) - 1 if end_index is None else end_index
    start = end - days + 1
    if start < 0 or end >= len(closes):
        return False
    return closes[end] >= max(closes[start : end + 1])


def stop_from_atr(
    entry: float,
    series: PriceSeries,
    *,
    atr_multiple: float = 1.5,
    max_loss_pct: float = 8.0,
    end_index: int | None = None,
) -> float:
    if entry <= 0:
        raise ValueError(f"entry must be positive, got {entry}")
    latest_atr = atr(series, 20, end_index=end_index)
    atr_stop = entry - (latest_atr or (entry * max_loss_pct / 100.0)) * atr_multiple
    capped_stop = entry * (1.0 - max_loss_pct / 100.0)
    return round(max(atr_stop, capped_stop), 4)


def bar_on_or_after(series: PriceSeries, day: date) -> int | None:
    for idx, bar in enumerate(series.bars):
        if bar.day >= day:
            return idx
    return None


def bar_on_or_before(series: PriceSeries, day: date) -> int | None:
    for idx in range(len(series.bars) - 1, -1, -1):
        if series.bars[idx].day <= day:
            return idx
    return None


def benchmark_alpha(
    candidate_return_pct: float,
    benchmark: PriceSeries,
    entry_day: date,
    exit_day: date,
) -> float | None:
    entry_idx = bar_on_or_after(benchmark, entry_day)
    exit_idx = bar_on_or_before(benchmark, exit_day)
    if entry_idx is None or exit_idx is None or exit_idx < entry_idx:
        return None
    start = benchmark.bars[entry_idx].open
    end = benchmark.bars[exit_idx].close
    if start <= 0:
        return None
    return candidate_return_pct - ((end / start - 1.0) * 100.0)


def latest_close(series: PriceSeries) -> float | None:
    return series.latest.close if series.latest is not None else None


def average_volume(series: PriceSeries, days: int = 20) -> float | None:
    bars = series.bars[-days:]
    if not bars:
        return None
    return statistics.fmean(bar.volume for bar in bars)
