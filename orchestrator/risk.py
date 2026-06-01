from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.ledger import Ledger
from core.strategy import Signal


@dataclass(frozen=True)
class SizedSignal:
    signal: Signal
    strategy: str
    stake: float


class RiskGate:
    """Portfolio-level risk filter applied before order execution.

    Enforces three hard limits:
    - total open exposure ≤ max_total_exposure_pct * bankroll
    - single position ≤ max_position_pct * bankroll
    - per-strategy daily loss > daily_loss_limit_pct * bankroll halts that strategy
    """

    def __init__(
        self,
        ledger: Ledger,
        max_total_exposure_pct: float = 0.20,
        max_position_pct: float = 0.02,
        daily_loss_limit_pct: float = 0.05,
    ) -> None:
        self._ledger = ledger
        self._max_exposure_pct = max_total_exposure_pct
        self._max_pos_pct = max_position_pct
        self._loss_limit_pct = daily_loss_limit_pct

    def approve(
        self, sized_signals: list[SizedSignal], bankroll: float
    ) -> list[SizedSignal]:
        """Return the subset of sized_signals that pass all risk limits."""
        open_pos = self._ledger.open_positions()
        current_exposure = sum(p["stake"] for p in open_pos)
        max_exposure = self._max_exposure_pct * bankroll
        max_position = self._max_pos_pct * bankroll

        today_str = date.today().isoformat()
        daily_pnl = self._daily_pnl_by_strategy(today_str)
        daily_loss_limit = self._loss_limit_pct * bankroll

        approved: list[SizedSignal] = []
        running_exposure = current_exposure

        for ss in sized_signals:
            if ss.stake > max_position:
                continue

            strat_pnl = daily_pnl.get(ss.strategy, 0.0)
            if strat_pnl < -daily_loss_limit:
                continue

            if running_exposure + ss.stake > max_exposure:
                continue

            approved.append(ss)
            running_exposure += ss.stake

        return approved

    def _daily_pnl_by_strategy(self, today_str: str) -> dict[str, float]:
        rows = self._ledger._con.execute(
            """SELECT strategy, COALESCE(SUM(pnl), 0.0) AS day_pnl
               FROM fills
               WHERE resolved = 1 AND DATE(timestamp) = ?
               GROUP BY strategy""",
            (today_str,),
        ).fetchall()
        return {r["strategy"]: float(r["day_pnl"]) for r in rows}
