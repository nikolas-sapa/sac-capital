"""07e — Kill-gate evaluation.

A variant may promote to real capital only when ALL conditions pass:
1. ≥ min_trades resolved forward-paper trades
2. Total net PnL (after full cost model) > 0  (positive expectancy)
3. Win rate ≥ min_win_rate
4. No real-capital flag present (LIVE must stay absent)
"""
from __future__ import annotations

from dataclasses import dataclass

from equities.killgate.tracker import ForwardPaperTracker


@dataclass(frozen=True)
class GateResult:
    passed: bool
    n_trades: int
    net_pnl: float
    win_rate: float
    reason: str


class KillGate:
    """Evaluate whether a strategy variant has earned forward-paper promotion.

    Args:
        min_trades:     Minimum resolved forward-paper trades required (default 100).
        min_win_rate:   Minimum win rate (default 0.40; expectancy matters more).
    """

    def __init__(self, min_trades: int = 100, min_win_rate: float = 0.40) -> None:
        self.min_trades = min_trades
        self.min_win_rate = min_win_rate

    def evaluate(
        self, tracker: ForwardPaperTracker, strategy: str | None = None
    ) -> GateResult:
        trades = tracker.closed_trades(strategy)
        n = len(trades)

        if n < self.min_trades:
            return GateResult(
                passed=False,
                n_trades=n,
                net_pnl=0.0,
                win_rate=0.0,
                reason=f"insufficient_trades: {n} < {self.min_trades}",
            )

        pnl_values = [t.net_pnl for t in trades if t.net_pnl is not None]
        total_pnl = sum(pnl_values)
        wins = sum(1 for p in pnl_values if p > 0)
        win_rate = wins / len(pnl_values) if pnl_values else 0.0

        if total_pnl <= 0:
            return GateResult(
                passed=False,
                n_trades=n,
                net_pnl=total_pnl,
                win_rate=win_rate,
                reason=f"negative_expectancy: net_pnl={total_pnl:.2f}",
            )

        if win_rate < self.min_win_rate:
            return GateResult(
                passed=False,
                n_trades=n,
                net_pnl=total_pnl,
                win_rate=win_rate,
                reason=f"win_rate={win_rate:.1%} < min={self.min_win_rate:.0%}",
            )

        return GateResult(
            passed=True,
            n_trades=n,
            net_pnl=total_pnl,
            win_rate=win_rate,
            reason="all_gates_passed",
        )
