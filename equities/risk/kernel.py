"""07d — Immutable risk kernel (sealed fuses).

This module enforces portfolio-level hard limits. In the paper phase it runs
in-process. When real capital is at stake (LIVE=true, not yet implemented),
it should run as a separate guardian process the strategy code cannot import
or modify.

Fuses enforced:
- Per-trade risk cap: max loss per trade ≤ risk_pct * capital (gap-aware)
- Max concurrent swing positions: ≤ max_positions (default 4)
- Per-name concentration: no single name > max_name_pct of swing sleeve
- Max daily loss: halts new entries for the day when breached
- Max total drawdown circuit-breaker: halts ALL trading
- Real-money promotion gate: LIVE flag absent by default
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from equities.risk.sizing import size_shares, _DEFAULT_GAP_PCT


@dataclass(frozen=True)
class SizedRecommendation:
    """A Recommendation approved and sized by the risk kernel."""

    # Forward-ref import avoided — using Any for the Recommendation type
    recommendation: Any
    shares: float
    approved: bool
    rejection_reason: str = ""


class RiskKernel:
    """Enforce immutable portfolio risk fuses before any position is opened.

    Args:
        capital:             Total swing sleeve capital (USD).
        risk_pct:            Max loss per trade as fraction of capital (default 0.02 = 2%).
        max_positions:       Max concurrent open swing positions (default 4).
        max_name_pct:        Max allocation to a single name (default 0.25 = 25%).
        daily_loss_limit_pct: Halts new entries when today's realized loss exceeds this
                              fraction of capital (default 0.05 = 5%).
        drawdown_limit_pct:  Circuit-breaker: halt ALL trading when drawdown from high-
                             water-mark exceeds this fraction (default 0.15 = 15%).
        gap_pct:             Stop-order gap penalty for sizing (default 2%).
    """

    def __init__(
        self,
        capital: float,
        risk_pct: float = 0.02,
        max_positions: int = 4,
        max_name_pct: float = 0.25,
        daily_loss_limit_pct: float = 0.05,
        drawdown_limit_pct: float = 0.15,
        gap_pct: float = _DEFAULT_GAP_PCT,
    ) -> None:
        self.capital = capital
        self.risk_pct = risk_pct
        self.max_positions = max_positions
        self.max_name_pct = max_name_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.drawdown_limit_pct = drawdown_limit_pct
        self.gap_pct = gap_pct

        self._high_water_mark = capital
        self._today = date.today().isoformat()
        self._daily_loss = 0.0
        self._halted = False  # circuit-breaker flag

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def approve(
        self,
        recommendation: Any,
        open_positions: list[dict[str, Any]],
        today_realized_loss: float = 0.0,
        current_equity: float | None = None,
    ) -> SizedRecommendation:
        """Approve or reject a Recommendation; return sized result.

        Args:
            recommendation:       The Recommendation from the analyst.
            open_positions:       Current open positions (list of dicts from EquityLedger).
            today_realized_loss:  Sum of today's closed pnl (negative = loss, positive = gain).
            current_equity:       Current total equity for drawdown check (None = skip).
        """
        # --- Circuit-breaker ---
        if self._halted:
            return SizedRecommendation(recommendation, 0.0, False, "circuit_breaker_tripped")

        # --- Drawdown check ---
        if current_equity is not None:
            self._high_water_mark = max(self._high_water_mark, current_equity)
            drawdown = (self._high_water_mark - current_equity) / self._high_water_mark
            if drawdown >= self.drawdown_limit_pct:
                self._halted = True
                return SizedRecommendation(recommendation, 0.0, False, f"drawdown={drawdown:.1%}_exceeds_{self.drawdown_limit_pct:.0%}")

        # --- Daily loss halt ---
        if today_realized_loss < -(self.daily_loss_limit_pct * self.capital):
            return SizedRecommendation(recommendation, 0.0, False, "daily_loss_limit_hit")

        sleeve = getattr(recommendation, "sleeve", None)
        is_core = sleeve is not None and str(sleeve.value) == "core"

        # --- CORE DCA: fixed fractional sizing (no stop required) ---
        if is_core:
            if recommendation.entry is None or recommendation.entry <= 0:
                return SizedRecommendation(recommendation, 0.0, False, "missing_entry")
            alloc_usd = self.capital * recommendation.size_pct
            shares = alloc_usd / recommendation.entry
            return SizedRecommendation(recommendation, round(shares, 6), True)

        # --- Concurrent position cap (swing only) ---
        swing_open = [p for p in open_positions if p.get("sleeve") == "swing"]
        if len(swing_open) >= self.max_positions:
            return SizedRecommendation(recommendation, 0.0, False, f"max_positions={self.max_positions}_reached")

        # --- Per-name concentration cap ---
        ticker = recommendation.instrument.ticker
        ticker_exposure = sum(
            p.get("shares", 0) * p.get("entry_price", 0)
            for p in swing_open
            if p.get("ticker") == ticker
        )
        if ticker_exposure / self.capital > self.max_name_pct:
            return SizedRecommendation(recommendation, 0.0, False, f"name_concentration_cap_{self.max_name_pct:.0%}_exceeded")

        # --- Gap-aware sizing (swing) ---
        if recommendation.stop_loss is None or recommendation.entry is None:
            return SizedRecommendation(recommendation, 0.0, False, "missing_stop_or_entry")

        shares = size_shares(
            capital=self.capital,
            risk_pct=self.risk_pct,
            entry=recommendation.entry,
            stop_loss=recommendation.stop_loss,
            gap_pct=self.gap_pct,
        )

        if shares <= 0:
            return SizedRecommendation(recommendation, 0.0, False, "zero_shares_after_sizing")

        # --- Max position size cap ---
        max_position_usd = self.max_name_pct * self.capital
        if shares * recommendation.entry > max_position_usd:
            shares = max_position_usd / recommendation.entry

        return SizedRecommendation(recommendation, round(shares, 6), True)
