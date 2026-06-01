from __future__ import annotations

from datetime import date


def _today() -> str:
    return date.today().isoformat()


class DailyBudget:
    """Guard daily Claude API spend for the equity analyst.

    Mirrors the DailyBudget in strategies/llm_probability/budget.py but
    lives here so the equities package is self-contained.
    """

    def __init__(self, daily_limit_usd: float = 1.0) -> None:
        self._limit = daily_limit_usd
        self._day = _today()
        self._spent = 0.0

    def _reset_if_new_day(self) -> None:
        today = _today()
        if today != self._day:
            self._day = today
            self._spent = 0.0

    def allow(self, estimated_cost_usd: float) -> bool:
        self._reset_if_new_day()
        return self._spent + estimated_cost_usd <= self._limit

    def record(self, actual_cost_usd: float) -> None:
        self._reset_if_new_day()
        self._spent += actual_cost_usd

    def spent_today(self) -> float:
        self._reset_if_new_day()
        return self._spent
