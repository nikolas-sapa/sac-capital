from __future__ import annotations

from dataclasses import dataclass

from core.ledger import Ledger


@dataclass(frozen=True)
class RollingStats:
    strategy: str
    n_resolved: int
    win_rate: float      # fraction of resolved trades that won
    roi: float           # realized pnl / total stake (can be negative)
    brier_score: float   # mean (predicted_prob - outcome)^2; 0 = perfect
    expectancy: float    # max(0, roi) * win_rate — allocation scoring metric


class StrategyStats:
    """Compute rolling performance metrics for each strategy from the ledger."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def rolling(self, strategy_name: str, window: int = 30) -> RollingStats:
        """Return stats over the last `window` resolved trades for `strategy_name`."""
        rows = self._ledger._con.execute(
            """SELECT fair_prob, won, pnl, stake
               FROM fills
               WHERE strategy = ? AND resolved = 1
               ORDER BY timestamp DESC
               LIMIT ?""",
            (strategy_name, window),
        ).fetchall()

        if not rows:
            return RollingStats(
                strategy=strategy_name,
                n_resolved=0,
                win_rate=0.0,
                roi=0.0,
                brier_score=0.25,  # worst-case calibration prior
                expectancy=0.0,
            )

        n = len(rows)
        wins = sum(1 for r in rows if r["won"] == 1)
        total_stake = sum(r["stake"] for r in rows)
        total_pnl = sum(r["pnl"] for r in rows)
        brier = sum((r["fair_prob"] - r["won"]) ** 2 for r in rows) / n

        win_rate = wins / n
        roi = total_pnl / total_stake if total_stake > 0 else 0.0
        expectancy = max(0.0, roi) * win_rate

        return RollingStats(
            strategy=strategy_name,
            n_resolved=n,
            win_rate=win_rate,
            roi=roi,
            brier_score=brier,
            expectancy=expectancy,
        )
