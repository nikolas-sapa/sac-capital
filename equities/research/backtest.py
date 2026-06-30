"""Small event backtester for paper strategy research candidates."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from core.assets.bar import Bar, PriceSeries
from equities.research.lag_rules import bar_on_or_after, benchmark_alpha, sma
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
) -> BacktestReport:
    benchmarks = {
        "SPY": prices.history("SPY", period="1y"),
        "QQQ": prices.history("QQQ", period="1y"),
        "SOXX": prices.history("SOXX", period="1y"),
    }
    trades = [
        trade
        for candidate in candidates
        if (trade := simulate_candidate(
            candidate,
            prices.history(candidate.ticker, period="1y"),
            prices.history(candidate.trunk, period="1y"),
            benchmarks=benchmarks,
            commission_bps=commission_bps,
            liquid_slippage_bps=liquid_slippage_bps,
            low_adv_slippage_bps=low_adv_slippage_bps,
            stop_gap_penalty_pct=stop_gap_penalty_pct,
        )) is not None
    ]
    return summarize_trades(trades)


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
    signal_idx = bar_on_or_after(series, candidate.entry_signal_at)
    if signal_idx is None:
        return None
    entry_delay = int(candidate.features.get("entry_delay_days", 0) or 0)
    entry_idx = signal_idx + 1 + entry_delay
    if entry_idx >= len(series.bars):
        return None

    max_holding_days = int(candidate.features.get("max_holding_days", 21) or 21)
    stop_loss = _float_feature(candidate, "stop_loss")
    take_profit = _float_feature(candidate, "take_profit")
    entry_bar = series.bars[entry_idx]
    entry_price = entry_bar.open
    if entry_price <= 0:
        return None

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
        if _trunk_invalidated(candidate, trunk_series, idx):
            exit_reason = "trunk_invalidated"
            break
        if idx - entry_idx >= max_holding_days:
            exit_reason = "time_stop"
            break

    exit_price = _exit_price(exit_bar, stop_loss, take_profit, exit_reason)
    gross_return_pct = (exit_price / entry_price - 1.0) * 100.0
    costs_pct = _costs_pct(series, commission_bps, liquid_slippage_bps, low_adv_slippage_bps)
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
        alpha_vs_spy_pct=_rounded_alpha(net_return_pct, benchmarks.get("SPY"), entry_idx, exit_idx),
        alpha_vs_qqq_pct=_rounded_alpha(net_return_pct, benchmarks.get("QQQ"), entry_idx, exit_idx),
        alpha_vs_soxx_pct=_rounded_alpha(net_return_pct, benchmarks.get("SOXX"), entry_idx, exit_idx),
    )


def summarize_trades(trades: list[BacktestTrade]) -> BacktestReport:
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
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    return BacktestReport(
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        trade_count=len(trades),
        expectancy_pct=round(expectancy, 4),
        hit_rate=round(hit_rate, 4),
        profit_factor=round(profit_factor, 4),
        max_drawdown_pct=round(_max_drawdown([trade.net_return_pct for trade in trades]), 4),
        pnl_by_strategy={key: round(value, 4) for key, value in sorted(pnl_by_strategy.items())},
        pnl_by_trunk={key: round(value, 4) for key, value in sorted(pnl_by_trunk.items())},
        trades=trades,
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


def _costs_pct(series: PriceSeries, commission_bps: float, liquid_slippage_bps: float, low_adv_slippage_bps: float) -> float:
    average_dollar_volume = _average_dollar_volume(series)
    slippage_bps = low_adv_slippage_bps if average_dollar_volume is not None and average_dollar_volume < 250_000_000 else liquid_slippage_bps
    return ((commission_bps + slippage_bps) * 2.0) / 100.0


def _average_dollar_volume(series: PriceSeries, days: int = 20) -> float | None:
    bars = series.bars[-days:]
    if not bars:
        return None
    return sum(bar.close * bar.volume for bar in bars) / len(bars)


def _trunk_invalidated(candidate: SupplyChainLagCandidate, trunk_series: PriceSeries, candidate_idx: int) -> bool:
    idx = min(candidate_idx, len(trunk_series.bars) - 1)
    if idx < 0:
        return False
    if candidate.strategy == "post_trunk_breakout_leaf_lag":
        trunk_sma20 = sma(trunk_series, 20, end_index=idx)
        return trunk_sma20 is not None and trunk_series.bars[idx].close < trunk_sma20
    if candidate.strategy == "semi_bottleneck_catch_up" and idx >= 20:
        start = trunk_series.bars[idx - 20].close
        end = trunk_series.bars[idx].close
        return start > 0 and (end / start - 1.0) * 100.0 < -10.0
    return False


def _rounded_alpha(net_return_pct: float, benchmark: PriceSeries | None, entry_idx: int, exit_idx: int) -> float | None:
    if benchmark is None:
        return None
    alpha = benchmark_alpha(net_return_pct, benchmark, entry_idx, exit_idx)
    return round(alpha, 4) if alpha is not None else None


def _max_drawdown(returns_pct: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for ret in returns_pct:
        equity += ret
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd
