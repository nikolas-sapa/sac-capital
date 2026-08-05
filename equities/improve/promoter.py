"""07f — Auto-promoter with kill-gate + cooldown rate-limit.

A variant may only be promoted when ALL four gates pass:
1. KillGate: ≥ min_trades forward-paper trades with positive net expectancy
2. Live paper track record: ≥ min_live_paper_trades after being deployed to paper
3. Cooldown: ≥ cooldown_days since the last promotion (prevents churn-on-luck)
4. Overfitting check: PBO/DSR verdict on the FULL set of tournament trials
   (see equities/eval/overfitting.py) — rejects a winner that's indistinguishable
   from the luckiest of many trials rather than a real edge.

This is "math-gated" autonomy per the spec: no per-trade human approval, but the
promotion itself is evidence-gated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Sequence

from equities.eval.overfitting import OverfittingChecker
from equities.improve.variants import ParameterVariant
from equities.killgate.gate import GateResult, KillGate
from equities.killgate.tracker import ForwardPaperTracker


@dataclass
class PromotionRecord:
    """Record of a variant that was promoted to the current champion."""

    variant: ParameterVariant
    promoted_on: date
    gate_result: GateResult


@dataclass(frozen=True)
class PromotionRejection:
    """Decision-artifact-style record of a blocked promotion attempt.

    Mirrors the stage+reason contract of `risk_decision_artifact` (see
    equities/research/artifacts.py) without depending on its Recommendation-
    shaped payload, which doesn't apply to a ParameterVariant.
    """

    variant_name: str
    stage: str
    reason: str
    decided_on: date = field(default_factory=date.today)


class AutoPromoter:
    """Gate + manage variant promotions.

    Args:
        gate:                  KillGate instance.
        cooldown_days:         Min days between promotions (default 14).
        min_live_paper_trades: Min live-paper trades before promoting (default 20).
        overfitting_checker:   OverfittingChecker instance (PBO/DSR thresholds).
    """

    def __init__(
        self,
        gate: KillGate | None = None,
        cooldown_days: int = 14,
        min_live_paper_trades: int = 20,
        overfitting_checker: OverfittingChecker | None = None,
    ) -> None:
        self._gate = gate or KillGate()
        self._cooldown_days = cooldown_days
        self._min_live = min_live_paper_trades
        self._overfitting = overfitting_checker or OverfittingChecker()
        self._history: list[PromotionRecord] = []
        self._rejections: list[PromotionRejection] = []
        self._current: ParameterVariant | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def try_promote(
        self,
        candidate: ParameterVariant,
        tracker: ForwardPaperTracker,
        *,
        trial_returns_matrix: Sequence[Sequence[float]],
        strategy: str | None = None,
        live_paper_trade_count: int = 0,
    ) -> bool:
        """Attempt to promote `candidate`. Returns True if promoted.

        All four gates must pass:
        1. KillGate (forward-paper evidence)
        2. Minimum live-paper trades deployed
        3. Cooldown from last promotion
        4. Overfitting check (PBO/DSR) on the full tournament trial set

        `trial_returns_matrix` is the FULL set of tournament trials (rows =
        periods, columns = variants — see TournamentResult.trial_returns_matrix),
        not just the candidate's own returns. A variant can only be promoted
        if the tournament it won is not, itself, indistinguishable from
        picking the luckiest of many noisy trials.
        """
        # Gate 1: forward-paper evidence
        gate_result = self._gate.evaluate(tracker, strategy)
        if not gate_result.passed:
            self._reject(candidate, stage="kill_gate", reason=gate_result.reason)
            return False

        # Gate 2: live-paper track record
        if live_paper_trade_count < self._min_live:
            self._reject(
                candidate, stage="live_paper",
                reason=f"live_paper_trades={live_paper_trade_count} < min={self._min_live}",
            )
            return False

        # Gate 3: cooldown
        if self._history:
            last_promo_date = self._history[-1].promoted_on
            days_since = date.today() - last_promo_date
            if days_since < timedelta(days=self._cooldown_days):
                self._reject(
                    candidate, stage="cooldown",
                    reason=f"days_since_last_promotion={days_since.days} < cooldown={self._cooldown_days}",
                )
                return False

        # Gate 4: overfitting check — fail closed on degenerate evidence
        # rather than trusting a PBO/DSR verdict computed from garbage.
        n_periods = len(trial_returns_matrix)
        n_trials = len(trial_returns_matrix[0]) if n_periods else 0
        if n_periods < 2 or n_trials < 2:
            self._reject(
                candidate, stage="overfitting",
                reason=f"insufficient_data_for_overfitting_check: periods={n_periods}, trials={n_trials}",
            )
            return False

        verdict = self._overfitting.evaluate(trial_returns_matrix)
        if not verdict["passed"]:
            self._reject(candidate, stage="overfitting", reason=verdict["reason"])
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

    def rejection_history(self) -> list[PromotionRejection]:
        return list(self._rejections)

    def _reject(self, candidate: ParameterVariant, *, stage: str, reason: str) -> None:
        self._rejections.append(
            PromotionRejection(variant_name=candidate.name, stage=stage, reason=reason)
        )

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
