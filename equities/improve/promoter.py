"""07f — Auto-promoter with kill-gate + cooldown rate-limit.

A variant may only be promoted when ALL three gates pass:
1. KillGate: ≥ min_trades forward-paper trades with positive net expectancy
2. Live paper track record: ≥ min_live_paper_trades after being deployed to paper
3. Cooldown: ≥ cooldown_days since the last promotion (prevents churn-on-luck)

This is "math-gated" autonomy per the spec: no per-trade human approval, but the
promotion itself is evidence-gated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from equities.improve.variants import ParameterVariant
from equities.killgate.gate import GateResult, KillGate
from equities.killgate.tracker import ForwardPaperTracker


@dataclass
class PromotionRecord:
    """Record of a variant that was promoted to the current champion."""

    variant: ParameterVariant
    promoted_on: date
    gate_result: GateResult


class AutoPromoter:
    """Gate + manage variant promotions.

    Args:
        gate:                 KillGate instance.
        cooldown_days:        Min days between promotions (default 14).
        min_live_paper_trades: Min live-paper trades before promoting (default 20).
    """

    def __init__(
        self,
        gate: KillGate | None = None,
        cooldown_days: int = 14,
        min_live_paper_trades: int = 20,
    ) -> None:
        self._gate = gate or KillGate()
        self._cooldown_days = cooldown_days
        self._min_live = min_live_paper_trades
        self._history: list[PromotionRecord] = []
        self._current: ParameterVariant | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def try_promote(
        self,
        candidate: ParameterVariant,
        tracker: ForwardPaperTracker,
        strategy: str | None = None,
        live_paper_trade_count: int = 0,
    ) -> bool:
        """Attempt to promote `candidate`. Returns True if promoted.

        All three gates must pass:
        1. KillGate (forward-paper evidence)
        2. Minimum live-paper trades deployed
        3. Cooldown from last promotion
        """
        # Gate 1: forward-paper evidence
        gate_result = self._gate.evaluate(tracker, strategy)
        if not gate_result.passed:
            return False

        # Gate 2: live-paper track record
        if live_paper_trade_count < self._min_live:
            return False

        # Gate 3: cooldown
        if self._history:
            last_promo_date = self._history[-1].promoted_on
            if date.today() - last_promo_date < timedelta(days=self._cooldown_days):
                return False

        self._history.append(
            PromotionRecord(
                variant=candidate,
                promoted_on=date.today(),
                gate_result=gate_result,
            )
        )
        self._current = candidate
        return True

    def current_params(self) -> dict[str, Any] | None:
        """Return the current champion params, or None if no promotion yet."""
        return dict(self._current.params) if self._current else None

    def promotion_history(self) -> list[PromotionRecord]:
        return list(self._history)

    def rollback(self) -> bool:
        """Revert to the previous champion. Returns True if a rollback occurred."""
        if len(self._history) < 2:
            return False
        self._history.pop()
        self._current = self._history[-1].variant
        return True
