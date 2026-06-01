from __future__ import annotations

from datetime import date


def _today() -> date:
    return date.today()


class DailyBudget:
    """Track LLM spend; deny calls that would push past the daily USD limit."""

    def __init__(self, limit_usd: float) -> None:
        self._limit = limit_usd
        self._day = _today()
        self._spent = 0.0

    def _maybe_reset(self) -> None:
        today = _today()
        if today != self._day:
            self._day = today
            self._spent = 0.0

    def allow(self, estimated_cost_usd: float) -> bool:
        self._maybe_reset()
        return self._spent + estimated_cost_usd <= self._limit

    def record(self, actual_cost_usd: float) -> None:
        self._maybe_reset()
        self._spent += actual_cost_usd

    def spent_today(self) -> float:
        self._maybe_reset()
        return self._spent
