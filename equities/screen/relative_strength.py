from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Protocol

from core.assets.bar import PriceSeries
from core.assets.instrument import Instrument


class HistoryProvider(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


@dataclass(frozen=True)
class RelativeStrengthEvidence:
    ticker: str
    rs_score: float
    rs_rank: int
    universe_size: int
    stock_return: float
    benchmark_return: float
    trend_ok: bool
    base_ok: bool
    breakout_volume: bool
    do_not_chase: bool
    evidence: str


class RelativeStrengthScanner:
    """Deterministic technical scanner for relative strength and breakout bases."""

    def __init__(
        self,
        prices: HistoryProvider,
        benchmark_tickers: tuple[str, ...] = ("SPY", "QQQ"),
        lookback_days: int = 63,
        base_window_days: int = 20,
        max_base_range_pct: float = 0.12,
        near_high_pct: float = 0.90,
        breakout_volume_multiple: float = 1.30,
        chase_5d_return: float = 0.15,
        chase_20d_return: float = 0.30,
    ) -> None:
        self._prices = prices
        self._benchmarks = benchmark_tickers
        self._lookback = lookback_days
        self._base_window = base_window_days
        self._max_base_range_pct = max_base_range_pct
        self._near_high_pct = near_high_pct
        self._breakout_volume_multiple = breakout_volume_multiple
        self._chase_5d_return = chase_5d_return
        self._chase_20d_return = chase_20d_return

    def scan(self, universe: list[Instrument]) -> dict[str, RelativeStrengthEvidence]:
        series_by_ticker = {
            inst.ticker: self._prices.history(inst.ticker, period="1y")
            for inst in universe
        }
        benchmark_return = self._benchmark_return()
        prelim: list[tuple[Instrument, PriceSeries, float, float]] = []
        for inst in universe:
            series = series_by_ticker[inst.ticker]
            stock_return = _return_over(series.closes, self._lookback)
            if stock_return is None:
                continue
            rs_score = stock_return - benchmark_return
            prelim.append((inst, series, stock_return, rs_score))

        ranked_scores = sorted((row[3] for row in prelim), reverse=True)
        universe_size = len(ranked_scores)
        results: dict[str, RelativeStrengthEvidence] = {}
        for inst, series, stock_return, rs_score in prelim:
            rs_rank = ranked_scores.index(rs_score) + 1
            trend_ok = _trend_ok(series.closes)
            base_ok = self._base_ok(series)
            breakout_volume = self._breakout_volume(series)
            do_not_chase = self._do_not_chase(series.closes)
            evidence = (
                f"RS rank {rs_rank}/{universe_size}; "
                f"RS score {rs_score:.1%} vs benchmarks; "
                f"trend_20_50_200={'pass' if trend_ok else 'fail'}; "
                f"base={'pass' if base_ok else 'fail'}; "
                f"breakout_volume={'yes' if breakout_volume else 'no'}; "
                f"do_not_chase={'yes' if do_not_chase else 'no'}"
            )
            results[inst.ticker] = RelativeStrengthEvidence(
                ticker=inst.ticker,
                rs_score=round(rs_score, 6),
                rs_rank=rs_rank,
                universe_size=universe_size,
                stock_return=round(stock_return, 6),
                benchmark_return=round(benchmark_return, 6),
                trend_ok=trend_ok,
                base_ok=base_ok,
                breakout_volume=breakout_volume,
                do_not_chase=do_not_chase,
                evidence=evidence,
            )
        return results

    def _benchmark_return(self) -> float:
        returns = [
            value
            for ticker in self._benchmarks
            if (value := _return_over(self._prices.history(ticker, period="1y").closes, self._lookback)) is not None
        ]
        return statistics.fmean(returns) if returns else 0.0

    def _base_ok(self, series: PriceSeries) -> bool:
        bars = series.bars
        if len(bars) < max(self._base_window, 40):
            return False
        window = bars[-self._base_window :]
        highs = [bar.high for bar in window]
        lows = [bar.low for bar in window]
        closes = [bar.close for bar in window]
        range_pct = (max(highs) - min(lows)) / closes[-1]
        if range_pct > self._max_base_range_pct:
            return False
        low, high = min(closes), max(closes)
        near_high = (closes[-1] - low) / (high - low) if high > low else 1.0
        if near_high < self._near_high_pct:
            return False
        recent_vol = _volatility(closes[-10:])
        prior_vol = _volatility([bar.close for bar in bars[-40:-20]])
        return recent_vol is not None and prior_vol is not None and recent_vol < prior_vol

    def _breakout_volume(self, series: PriceSeries) -> bool:
        bars = series.bars
        if len(bars) < self._base_window + 1:
            return False
        avg_volume = statistics.fmean(bar.volume for bar in bars[-self._base_window - 1 : -1])
        return avg_volume > 0 and bars[-1].volume >= avg_volume * self._breakout_volume_multiple

    def _do_not_chase(self, closes: list[float]) -> bool:
        ret_5 = _return_over(closes, 5)
        ret_20 = _return_over(closes, 20)
        return (ret_5 is not None and ret_5 > self._chase_5d_return) or (
            ret_20 is not None and ret_20 > self._chase_20d_return
        )


def _return_over(closes: list[float], days: int) -> float | None:
    if len(closes) <= days:
        return None
    start = closes[-days - 1]
    end = closes[-1]
    if start <= 0:
        return None
    return (end / start) - 1.0


def _sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return statistics.fmean(closes[-window:])


def _trend_ok(closes: list[float]) -> bool:
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    if sma20 is None or sma50 is None or sma200 is None:
        return False
    return closes[-1] > sma20 > sma50 > sma200


def _volatility(closes: list[float]) -> float | None:
    if len(closes) < 3:
        return None
    returns = []
    for previous, current in zip(closes, closes[1:]):
        if previous <= 0:
            return None
        returns.append((current / previous) - 1.0)
    return statistics.pstdev(returns)
