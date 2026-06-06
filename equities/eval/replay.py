from __future__ import annotations

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
    ) -> None:
        self._prices = prices
        self._holding_days = holding_days
        self._min_trades = min_trades

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
        )


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
        )

    wins = [trade.pnl_pct for trade in trades if trade.pnl_pct > 0]
    losses = [trade.pnl_pct for trade in trades if trade.pnl_pct <= 0]
    sector_counts: dict[str, int] = {}
    for trade in trades:
        sector_counts[trade.sector or "Unknown"] = sector_counts.get(trade.sector or "Unknown", 0) + 1
    max_sector_concentration = max(sector_counts.values()) / len(trades)
    expectancy = sum(trade.pnl_pct for trade in trades) / len(trades)
    enough_sample = len(trades) >= min_trades
    positive_validation = expectancy > 0
    rejection = ""
    if not enough_sample:
        rejection = f"sample_size_below_min_trades={min_trades}"
    elif not positive_validation:
        rejection = "expectancy_not_positive"

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
        promotable=enough_sample and positive_validation,
        rejection_reason=rejection,
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
        f"promotable={metrics.promotable} reason={metrics.rejection_reason or 'ok'}"
    )
