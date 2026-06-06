from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from core.assets.bar import Bar, PriceSeries
from equities.research.artifacts import EquityResearchArtifact


class HistoryProvider(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


@dataclass(frozen=True)
class ReplayTrade:
    ticker: str
    sector: str
    entry_day: date
    exit_day: date
    entry_price: float
    exit_price: float
    pnl_pct: float
    outcome: str
    artifact_id: str
    r_multiple: float = 0.0
    benchmark_return_pct: float | None = None
    catalyst_type: str = ""


@dataclass(frozen=True)
class ReplayMetrics:
    trade_count: int
    expectancy_pct: float
    win_rate: float
    average_win_pct: float
    average_loss_pct: float
    max_drawdown_pct: float
    average_exposure_days: float
    max_sector_concentration: float
    promotable: bool
    rejection_reason: str = ""
    profit_factor: float = 0.0
    median_return_pct: float = 0.0
    return_std_pct: float = 0.0
    sharpe_like: float = 0.0
    sortino_like: float = 0.0
    max_consecutive_losses: int = 0
    average_r_multiple: float = 0.0
    alpha_vs_benchmark_pct: float = 0.0
    beta_vs_benchmark: float = 0.0
    sector_expectancy_pct: dict[str, float] | None = None
    catalyst_expectancy_pct: dict[str, float] | None = None
    exit_distribution: dict[str, int] | None = None


@dataclass(frozen=True)
class ReplayReport:
    train: ReplayMetrics
    validation: ReplayMetrics
    train_trades: list[ReplayTrade]
    validation_trades: list[ReplayTrade]

    def to_text(self) -> str:
        return "\n".join([
            "Equity artifact replay report",
            _metrics_line("train", self.train),
            _metrics_line("validation", self.validation),
        ])


class ArtifactReplayEvaluator:
    """Replay approved research artifacts against historical daily prices."""

    def __init__(
        self,
        prices: HistoryProvider,
        holding_days: int = 20,
        min_trades: int = 20,
        benchmark_ticker: str = "SPY",
    ) -> None:
        self._prices = prices
        self._holding_days = holding_days
        self._min_trades = min_trades
        self._benchmark_ticker = benchmark_ticker

    def evaluate(
        self,
        artifacts: list[EquityResearchArtifact],
        validation_start: date,
    ) -> ReplayReport:
        trades = [
            trade
            for artifact in artifacts
            if (trade := self._replay_one(artifact)) is not None
        ]
        train = [trade for trade in trades if trade.entry_day < validation_start]
        validation = [trade for trade in trades if trade.entry_day >= validation_start]
        return ReplayReport(
            train=_metrics(train, self._min_trades),
            validation=_metrics(validation, self._min_trades),
            train_trades=train,
            validation_trades=validation,
        )

    def _replay_one(self, artifact: EquityResearchArtifact) -> ReplayTrade | None:
        if artifact.decision != "approved" or not artifact.output_json:
            return None
        try:
            entry_limit = float(artifact.output_json["entry"])
            stop = float(artifact.output_json["stop_loss"])
            target = float(artifact.output_json["take_profit"])
        except (KeyError, TypeError, ValueError):
            return None
        if entry_limit <= 0 or stop <= 0 or target <= entry_limit:
            return None

        bars = self._prices.history(artifact.ticker, period="1y").bars
        as_of = _parse_day(artifact.as_of)
        entry_index = _first_bar_index_on_or_after(bars, as_of)
        if entry_index is None:
            return None

        entry_bar = bars[entry_index]
        entry_price = min(entry_limit, entry_bar.close)
        exit_bar = bars[min(len(bars) - 1, entry_index + self._holding_days)]
        exit_price = exit_bar.close
        outcome = "time"
        for bar in bars[entry_index + 1 : entry_index + self._holding_days + 1]:
            if bar.low <= stop:
                exit_bar = bar
                exit_price = stop
                outcome = "stop"
                break
            if bar.high >= target:
                exit_bar = bar
                exit_price = target
                outcome = "target"
                break

        pnl_pct = (exit_price / entry_price) - 1.0
        candidate = artifact.candidate or {}
        benchmark_return = self._benchmark_return(as_of, entry_index, exit_bar.day)
        risk_per_share = entry_price - stop
        r_multiple = ((exit_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0.0
        return ReplayTrade(
            ticker=artifact.ticker,
            sector=str(candidate.get("sector", "")),
            entry_day=entry_bar.day,
            exit_day=exit_bar.day,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_pct=round(pnl_pct, 6),
            outcome=outcome,
            artifact_id=artifact.artifact_id,
            r_multiple=round(r_multiple, 4),
            benchmark_return_pct=benchmark_return,
            catalyst_type=str(candidate.get("event_type", "")),
        )

    def _benchmark_return(
        self,
        as_of: date,
        ticker_entry_index: int,
        exit_day: date,
    ) -> float | None:
        try:
            bars = self._prices.history(self._benchmark_ticker, period="1y").bars
            entry_index = _first_bar_index_on_or_after(bars, as_of)
            if entry_index is None:
                return None
            exit_index = _first_bar_index_on_or_after(bars, exit_day)
            if exit_index is None:
                exit_index = min(len(bars) - 1, ticker_entry_index + self._holding_days)
            if exit_index <= entry_index:
                return None
            entry = bars[entry_index].close
            if entry <= 0:
                return None
            return round((bars[exit_index].close / entry) - 1.0, 6)
        except Exception:
            return None


def _metrics(trades: list[ReplayTrade], min_trades: int) -> ReplayMetrics:
    if not trades:
        return ReplayMetrics(
            trade_count=0,
            expectancy_pct=0.0,
            win_rate=0.0,
            average_win_pct=0.0,
            average_loss_pct=0.0,
            max_drawdown_pct=0.0,
            average_exposure_days=0.0,
            max_sector_concentration=0.0,
            promotable=False,
            rejection_reason=f"sample_size_below_min_trades={min_trades}",
            sector_expectancy_pct={},
            catalyst_expectancy_pct={},
            exit_distribution={},
        )

    wins = [trade.pnl_pct for trade in trades if trade.pnl_pct > 0]
    losses = [trade.pnl_pct for trade in trades if trade.pnl_pct <= 0]
    sector_counts: dict[str, int] = {}
    for trade in trades:
        sector_counts[trade.sector or "Unknown"] = sector_counts.get(trade.sector or "Unknown", 0) + 1
    max_sector_concentration = max(sector_counts.values()) / len(trades)
    expectancy = sum(trade.pnl_pct for trade in trades) / len(trades)
    returns = [trade.pnl_pct for trade in trades]
    std = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    downside = [min(0.0, trade.pnl_pct) for trade in trades]
    downside_std = statistics.pstdev(downside) if len(downside) > 1 else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    benchmark_pairs = [
        (trade.pnl_pct, trade.benchmark_return_pct)
        for trade in trades
        if trade.benchmark_return_pct is not None
    ]
    alpha = (
        sum(ret - bench for ret, bench in benchmark_pairs) / len(benchmark_pairs)
        if benchmark_pairs
        else 0.0
    )
    beta = _beta(benchmark_pairs)
    exit_distribution: dict[str, int] = {}
    for trade in trades:
        exit_distribution[trade.outcome] = exit_distribution.get(trade.outcome, 0) + 1
    enough_sample = len(trades) >= min_trades
    positive_validation = expectancy > 0
    positive_alpha = alpha > 0 if benchmark_pairs else True
    rejection = ""
    if not enough_sample:
        rejection = f"sample_size_below_min_trades={min_trades}"
    elif not positive_validation:
        rejection = "expectancy_not_positive"
    elif profit_factor <= 1.2:
        rejection = "profit_factor_below_1.2"
    elif not positive_alpha:
        rejection = "alpha_vs_benchmark_not_positive"

    return ReplayMetrics(
        trade_count=len(trades),
        expectancy_pct=round(expectancy * 100, 4),
        win_rate=round(len(wins) / len(trades), 4),
        average_win_pct=round((sum(wins) / len(wins) * 100) if wins else 0.0, 4),
        average_loss_pct=round((sum(losses) / len(losses) * 100) if losses else 0.0, 4),
        max_drawdown_pct=round(_max_drawdown_pct(trades), 4),
        average_exposure_days=round(
            sum((trade.exit_day - trade.entry_day).days for trade in trades) / len(trades),
            4,
        ),
        max_sector_concentration=round(max_sector_concentration, 4),
        promotable=enough_sample and positive_validation and profit_factor > 1.2 and positive_alpha,
        rejection_reason=rejection,
        profit_factor=round(profit_factor, 4) if math.isfinite(profit_factor) else math.inf,
        median_return_pct=round(statistics.median(returns) * 100, 4),
        return_std_pct=round(std * 100, 4),
        sharpe_like=round(expectancy / std, 4) if std > 0 else 0.0,
        sortino_like=round(expectancy / downside_std, 4) if downside_std > 0 else 0.0,
        max_consecutive_losses=_max_consecutive_losses(trades),
        average_r_multiple=round(sum(trade.r_multiple for trade in trades) / len(trades), 4),
        alpha_vs_benchmark_pct=round(alpha * 100, 4),
        beta_vs_benchmark=round(beta, 4),
        sector_expectancy_pct=_group_expectancy(trades, "sector"),
        catalyst_expectancy_pct=_group_expectancy(trades, "catalyst_type"),
        exit_distribution=exit_distribution,
    )


def _max_drawdown_pct(trades: list[ReplayTrade]) -> float:
    equity = 1.0
    high = 1.0
    max_drawdown = 0.0
    for trade in sorted(trades, key=lambda item: item.entry_day):
        equity *= 1.0 + trade.pnl_pct
        high = max(high, equity)
        drawdown = (high - equity) / high
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown * 100


def _max_consecutive_losses(trades: list[ReplayTrade]) -> int:
    longest = current = 0
    for trade in sorted(trades, key=lambda item: item.entry_day):
        if trade.pnl_pct <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _beta(pairs: list[tuple[float, float | None]]) -> float:
    clean = [(ret, bench) for ret, bench in pairs if bench is not None]
    if len(clean) < 2:
        return 0.0
    returns = [ret for ret, _bench in clean]
    benchmark = [bench for _ret, bench in clean]
    bench_mean = sum(benchmark) / len(benchmark)
    variance = sum((item - bench_mean) ** 2 for item in benchmark)
    if variance == 0:
        return 0.0
    return sum((ret - sum(returns) / len(returns)) * (bench - bench_mean) for ret, bench in clean) / variance


def _group_expectancy(trades: list[ReplayTrade], attr: str) -> dict[str, float]:
    groups: dict[str, list[float]] = {}
    for trade in trades:
        label = str(getattr(trade, attr) or "Unknown")
        groups.setdefault(label, []).append(trade.pnl_pct)
    return {
        label: round((sum(values) / len(values)) * 100, 4)
        for label, values in sorted(groups.items())
    }


def _parse_day(value: str) -> date:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return date.fromisoformat(value[:10])


def _first_bar_index_on_or_after(bars: list[Bar], day: date) -> int | None:
    for idx, bar in enumerate(bars):
        if bar.day >= day:
            return idx
    return None


def _metrics_line(label: str, metrics: ReplayMetrics) -> str:
    return (
        f"{label}: trades={metrics.trade_count} expectancy={metrics.expectancy_pct:.2f}% "
        f"win_rate={metrics.win_rate:.2%} avg_win={metrics.average_win_pct:.2f}% "
        f"avg_loss={metrics.average_loss_pct:.2f}% max_dd={metrics.max_drawdown_pct:.2f}% "
        f"avg_exposure_days={metrics.average_exposure_days:.1f} "
        f"max_sector_concentration={metrics.max_sector_concentration:.2%} "
        f"profit_factor={metrics.profit_factor:.2f} median={metrics.median_return_pct:.2f}% "
        f"std={metrics.return_std_pct:.2f}% sharpe_like={metrics.sharpe_like:.2f} "
        f"sortino_like={metrics.sortino_like:.2f} max_consecutive_losses={metrics.max_consecutive_losses} "
        f"avg_r={metrics.average_r_multiple:.2f} alpha_vs_benchmark={metrics.alpha_vs_benchmark_pct:.2f}% "
        f"beta_vs_benchmark={metrics.beta_vs_benchmark:.2f} exits={metrics.exit_distribution or {}} "
        f"promotable={metrics.promotable} reason={metrics.rejection_reason or 'ok'}"
    )
