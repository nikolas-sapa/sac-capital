"""Small event backtester for paper strategy research candidates."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

from core.assets.bar import Bar, PriceSeries
from equities.research.lag_rules import bar_on_or_after, bar_on_or_before, benchmark_alpha, sma
from equities.screen.supply_chain_lag_screen import SupplyChainLagCandidate


class HistoryProvider(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


@dataclass(frozen=True)
class BacktestTrade:
    strategy: str
    ticker: str
    trunk: str
    signal_day: str
    entry_day: str
    exit_day: str
    entry_price: float
    exit_price: float
    gross_return_pct: float
    net_return_pct: float
    exit_reason: str
    alpha_vs_spy_pct: float | None = None
    alpha_vs_qqq_pct: float | None = None
    alpha_vs_soxx_pct: float | None = None


@dataclass(frozen=True)
class BacktestReport:
    generated_at: str
    trade_count: int
    expectancy_pct: float
    hit_rate: float
    profit_factor: float
    max_drawdown_pct: float
    pnl_by_strategy: dict[str, float]
    pnl_by_trunk: dict[str, float]
    trades: list[BacktestTrade]
    skipped_count: int = 0
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    data_errors: list[str] = field(default_factory=list)
    actionable: bool = False
    rejection_reason: str = ""
    max_ticker_concentration: float = 0.0
    max_trunk_concentration: float = 0.0
    params: dict[str, float | str] = field(default_factory=dict)

    def as_record(self) -> dict:
        record = asdict(self)
        record["trades"] = [asdict(trade) for trade in self.trades]
        return record


def run_backtest(
    candidates: list[SupplyChainLagCandidate],
    prices: HistoryProvider,
    *,
    commission_bps: float = 10.0,
    liquid_slippage_bps: float = 5.0,
    low_adv_slippage_bps: float = 20.0,
    stop_gap_penalty_pct: float = 2.0,
    period: str = "1y",
) -> BacktestReport:
    data_errors: list[str] = []
    history_cache: dict[str, PriceSeries] = {}
    benchmarks = {
        ticker: _cached_history(prices, ticker, period, data_errors, history_cache)
        for ticker in ("SPY", "QQQ", "SOXX")
    }
    trades: list[BacktestTrade] = []
    skipped_reasons: dict[str, int] = {}
    for candidate in candidates:
        series = _cached_history(prices, candidate.ticker, period, data_errors, history_cache)
        trunk_series = _cached_history(prices, candidate.trunk, period, data_errors, history_cache)
        trade, reason = _simulate_candidate(
            candidate,
            series,
            trunk_series,
            benchmarks=benchmarks,
            commission_bps=commission_bps,
            liquid_slippage_bps=liquid_slippage_bps,
            low_adv_slippage_bps=low_adv_slippage_bps,
            stop_gap_penalty_pct=stop_gap_penalty_pct,
        )
        if trade is None:
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        else:
            trades.append(trade)
    return summarize_trades(
        trades,
        skipped_reasons=skipped_reasons,
        data_errors=data_errors,
        params={
            "period": period,
            "commission_bps": commission_bps,
            "liquid_slippage_bps": liquid_slippage_bps,
            "low_adv_slippage_bps": low_adv_slippage_bps,
            "stop_gap_penalty_pct": stop_gap_penalty_pct,
        },
    )


def simulate_candidate(
    candidate: SupplyChainLagCandidate,
    series: PriceSeries,
    trunk_series: PriceSeries,
    *,
    benchmarks: dict[str, PriceSeries] | None = None,
    commission_bps: float = 10.0,
    liquid_slippage_bps: float = 5.0,
    low_adv_slippage_bps: float = 20.0,
    stop_gap_penalty_pct: float = 2.0,
) -> BacktestTrade | None:
    trade, _reason = _simulate_candidate(
        candidate,
        series,
        trunk_series,
        benchmarks=benchmarks,
        commission_bps=commission_bps,
        liquid_slippage_bps=liquid_slippage_bps,
        low_adv_slippage_bps=low_adv_slippage_bps,
        stop_gap_penalty_pct=stop_gap_penalty_pct,
    )
    return trade


def _simulate_candidate(
    candidate: SupplyChainLagCandidate,
    series: PriceSeries,
    trunk_series: PriceSeries,
    *,
    benchmarks: dict[str, PriceSeries] | None = None,
    commission_bps: float = 10.0,
    liquid_slippage_bps: float = 5.0,
    low_adv_slippage_bps: float = 20.0,
    stop_gap_penalty_pct: float = 2.0,
) -> tuple[BacktestTrade | None, str]:
    if not series.bars:
        return None, "no_price_data"
    signal_idx = bar_on_or_after(series, candidate.entry_signal_at)
    if signal_idx is None:
        return None, "no_signal_bar"
    entry_delay = int(candidate.features.get("entry_delay_days", 0) or 0)
    entry_idx = signal_idx + 1 + entry_delay
    if entry_idx >= len(series.bars):
        return None, "no_future_entry_bar"

    max_holding_days = int(candidate.features.get("max_holding_days", 21) or 21)
    stop_loss = _float_feature(candidate, "stop_loss")
    take_profit = _float_feature(candidate, "take_profit")
    entry_bar = series.bars[entry_idx]
    entry_price = entry_bar.open
    if entry_price <= 0:
        return None, "bad_entry_price"

    exit_idx = entry_idx
    exit_bar = series.bars[entry_idx]
    exit_reason = "time_stop"
    for idx in range(entry_idx, min(len(series.bars), entry_idx + max_holding_days + 1)):
        bar = series.bars[idx]
        exit_idx = idx
        exit_bar = bar
        if stop_loss is not None and bar.low <= stop_loss:
            exit_reason = "stop_hit"
            break
        if take_profit is not None and bar.high >= take_profit:
            exit_reason = "target_hit"
            break
        if _trunk_invalidated(candidate, trunk_series, bar.day):
            exit_reason = "trunk_invalidated"
            break
        if idx - entry_idx >= max_holding_days:
            exit_reason = "time_stop"
            break

    exit_price = _exit_price(exit_bar, stop_loss, take_profit, exit_reason)
    gross_return_pct = (exit_price / entry_price - 1.0) * 100.0
    costs_pct = _costs_pct(series, entry_idx, commission_bps, liquid_slippage_bps, low_adv_slippage_bps)
    if exit_reason == "stop_hit":
        costs_pct += stop_gap_penalty_pct
    net_return_pct = gross_return_pct - costs_pct

    benchmarks = benchmarks or {}
    return BacktestTrade(
        strategy=candidate.strategy,
        ticker=candidate.ticker,
        trunk=candidate.trunk,
        signal_day=series.bars[signal_idx].day.isoformat(),
        entry_day=entry_bar.day.isoformat(),
        exit_day=exit_bar.day.isoformat(),
        entry_price=round(entry_price, 4),
        exit_price=round(exit_price, 4),
        gross_return_pct=round(gross_return_pct, 4),
        net_return_pct=round(net_return_pct, 4),
        exit_reason=exit_reason,
        alpha_vs_spy_pct=_rounded_alpha(net_return_pct, benchmarks.get("SPY"), entry_bar.day, exit_bar.day),
        alpha_vs_qqq_pct=_rounded_alpha(net_return_pct, benchmarks.get("QQQ"), entry_bar.day, exit_bar.day),
        alpha_vs_soxx_pct=_rounded_alpha(net_return_pct, benchmarks.get("SOXX"), entry_bar.day, exit_bar.day),
    ), ""


def summarize_trades(
    trades: list[BacktestTrade],
    *,
    skipped_reasons: dict[str, int] | None = None,
    data_errors: list[str] | None = None,
    params: dict[str, float | str] | None = None,
) -> BacktestReport:
    skipped_reasons = skipped_reasons or {}
    data_errors = data_errors or []
    pnl_by_strategy: dict[str, float] = {}
    pnl_by_trunk: dict[str, float] = {}
    for trade in trades:
        pnl_by_strategy[trade.strategy] = pnl_by_strategy.get(trade.strategy, 0.0) + trade.net_return_pct
        pnl_by_trunk[trade.trunk] = pnl_by_trunk.get(trade.trunk, 0.0) + trade.net_return_pct
    wins = [trade.net_return_pct for trade in trades if trade.net_return_pct > 0]
    losses = [trade.net_return_pct for trade in trades if trade.net_return_pct < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    expectancy = sum(trade.net_return_pct for trade in trades) / len(trades) if trades else 0.0
    hit_rate = len(wins) / len(trades) if trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    rejection = ""
    if data_errors:
        rejection = "data_errors"
    elif not trades:
        rejection = "no_trades"
    return BacktestReport(
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        trade_count=len(trades),
        expectancy_pct=round(expectancy, 4),
        hit_rate=round(hit_rate, 4),
        profit_factor=round(profit_factor, 4) if math.isfinite(profit_factor) else 999.0,
        max_drawdown_pct=round(_max_drawdown(trades), 4),
        pnl_by_strategy={key: round(value, 4) for key, value in sorted(pnl_by_strategy.items())},
        pnl_by_trunk={key: round(value, 4) for key, value in sorted(pnl_by_trunk.items())},
        trades=trades,
        skipped_count=sum(skipped_reasons.values()),
        skipped_reasons=dict(sorted(skipped_reasons.items())),
        data_errors=data_errors,
        actionable=not rejection,
        rejection_reason=rejection,
        max_ticker_concentration=_max_concentration([trade.ticker for trade in trades]),
        max_trunk_concentration=_max_concentration([trade.trunk for trade in trades]),
        params=params or {},
    )


def append_backtest_report(path: Path, report: BacktestReport) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(report.as_record(), sort_keys=True) + "\n")


def _float_feature(candidate: SupplyChainLagCandidate, key: str) -> float | None:
    value = candidate.features.get(key)
    return float(value) if isinstance(value, int | float) else None


def _exit_price(bar: Bar, stop_loss: float | None, take_profit: float | None, reason: str) -> float:
    if reason == "stop_hit" and stop_loss is not None:
        return min(stop_loss, bar.open)
    if reason == "target_hit" and take_profit is not None:
        return max(take_profit, bar.open)
    return bar.close


def _costs_pct(
    series: PriceSeries,
    entry_idx: int,
    commission_bps: float,
    liquid_slippage_bps: float,
    low_adv_slippage_bps: float,
) -> float:
    average_dollar_volume = _average_dollar_volume(series, entry_idx=entry_idx)
    slippage_bps = (
        low_adv_slippage_bps
        if average_dollar_volume is not None and average_dollar_volume < 250_000_000
        else liquid_slippage_bps
    )
    if average_dollar_volume is None:
        slippage_bps = low_adv_slippage_bps
    return ((commission_bps + slippage_bps) * 2.0) / 100.0


def _average_dollar_volume(series: PriceSeries, *, entry_idx: int, days: int = 20) -> float | None:
    bars = series.bars[max(0, entry_idx - days) : entry_idx]
    if not bars:
        return None
    return sum(bar.close * bar.volume for bar in bars) / len(bars)


def _trunk_invalidated(candidate: SupplyChainLagCandidate, trunk_series: PriceSeries, candidate_day: date) -> bool:
    idx = bar_on_or_before(trunk_series, candidate_day)
    if idx is None:
        return False
    if candidate.strategy == "post_trunk_breakout_leaf_lag":
        trunk_sma20 = sma(trunk_series, 20, end_index=idx)
        return trunk_sma20 is not None and trunk_series.bars[idx].close < trunk_sma20
    if candidate.strategy == "semi_bottleneck_catch_up" and idx >= 20:
        start = trunk_series.bars[idx - 20].close
        end = trunk_series.bars[idx].close
        return start > 0 and (end / start - 1.0) * 100.0 < -10.0
    return False


def _rounded_alpha(
    net_return_pct: float,
    benchmark: PriceSeries | None,
    entry_day: date,
    exit_day: date,
) -> float | None:
    if benchmark is None:
        return None
    alpha = benchmark_alpha(net_return_pct, benchmark, entry_day, exit_day)
    return round(alpha, 4) if alpha is not None else None


def _max_drawdown(trades: list[BacktestTrade]) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for trade in sorted(trades, key=lambda item: item.entry_day):
        equity *= 1.0 + trade.net_return_pct / 100.0
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    return max_dd * 100.0


def _max_concentration(labels: list[str]) -> float:
    if not labels:
        return 0.0
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return round(max(counts.values()) / len(labels), 4)


def _history(prices: HistoryProvider, ticker: str, period: str, data_errors: list[str]) -> PriceSeries:
    try:
        series = prices.history(ticker, period=period)
    except Exception as exc:
        data_errors.append(f"{ticker}:exception:{exc}")
        return PriceSeries(ticker=ticker, bars=[])
    if not series.bars:
        data_errors.append(f"{ticker}:empty")
    return series


def _cached_history(
    prices: HistoryProvider,
    ticker: str,
    period: str,
    data_errors: list[str],
    cache: dict[str, PriceSeries],
) -> PriceSeries:
    if ticker not in cache:
        cache[ticker] = _history(prices, ticker, period, data_errors)
    return cache[ticker]
