"""07d — Immutable risk kernel (sealed fuses).

This module enforces portfolio-level hard limits. In the paper phase it runs
in-process. When real capital is at stake (LIVE=true, not yet implemented),
it should run as a separate guardian process the strategy code cannot import
or modify.

Fuses enforced:
- Per-trade risk cap: max loss per trade ≤ risk_pct * capital (gap-aware)
- Max concurrent swing positions: ≤ max_positions (default 4)
- Per-name concentration: no single name > max_name_pct of swing sleeve
- Return correlation: blocks adds too correlated (pairwise or vs. portfolio
  avg) with the open book — catches same-bet exposure sector labels miss
  (see equities/risk/correlation.py)
- Max daily loss: halts new entries for the day when breached
- Max total drawdown circuit-breaker: halts ALL trading
- Real-money promotion gate: LIVE flag absent by default
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from equities.risk.sizing import empirical_kelly_risk_pct, size_shares, _DEFAULT_GAP_PCT


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
        min_rr:              Minimum (take_profit-entry)/(entry-stop_loss) to approve a
                             swing trade (default 2.0). 0 disables the gate.
        kelly_fraction:      Fractional Kelly applied to swing risk once a confidence
                             band has enough closed trades (default 0.0 = disabled).
        kelly_min_trades:    Closed trades required in a band before Kelly sizing
                             replaces flat risk_pct (default 30).
        win_stats_lookup:    Callable[[float], tuple[int, float]] mapping confidence ->
                             (n_closed_in_band, win_rate). Required for Kelly sizing.
        max_pairwise_corr:   Max allowed return correlation vs. any single open position
                             (default 0.7). Requires correlation_checker to take effect.
        max_portfolio_corr:  Max allowed average return correlation vs. the whole open
                             book (default 0.5). Requires correlation_checker to take effect.
        correlation_checker: equities.risk.correlation.CorrelationChecker instance (or
                             None to disable the gate — e.g. provider unavailable).
    """

    def __init__(
        self,
        capital: float,
        risk_pct: float = 0.02,
        max_positions: int = 4,
        max_name_pct: float = 0.25,
        max_sector_pct: float = 0.35,
        daily_loss_limit_pct: float = 0.05,
        drawdown_limit_pct: float = 0.15,
        gap_pct: float = _DEFAULT_GAP_PCT,
        min_rr: float = 2.0,
        kelly_fraction: float = 0.0,
        kelly_min_trades: int = 30,
        win_stats_lookup: Any = None,
        state_path: Path | None = None,
        max_pairwise_corr: float = 0.7,
        max_portfolio_corr: float = 0.5,
        correlation_checker: Any = None,
    ) -> None:
        if capital <= 0:
            raise ValueError(f"RiskKernel capital must be positive, got {capital}")
        self.capital = capital
        self.risk_pct = risk_pct
        self.max_positions = max_positions
        self.max_name_pct = max_name_pct
        self.max_sector_pct = max_sector_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.drawdown_limit_pct = drawdown_limit_pct
        self.gap_pct = gap_pct
        self.min_rr = min_rr
        self.kelly_fraction = kelly_fraction
        self.kelly_min_trades = kelly_min_trades
        self._win_stats_lookup = win_stats_lookup
        self.max_pairwise_corr = max_pairwise_corr
        self.max_portfolio_corr = max_portfolio_corr
        self._correlation_checker = correlation_checker

        self._state_path = state_path
        self._high_water_mark = capital
        self._today = date.today().isoformat()
        self._daily_loss = 0.0
        self._halted = False  # circuit-breaker flag

        # Load persisted state if available
        if state_path is not None:
            from equities.risk.state import load_kernel_state
            saved = load_kernel_state(state_path)
            if float(saved.get("capital", capital)) == capital:
                self._high_water_mark = max(capital, float(saved.get("high_water_mark", capital)))
                self._halted = bool(saved.get("halted", False))
            # else: bankroll changed in config -> stale hwm/halt discarded, fresh baseline

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def approve(
        self,
        recommendation: Any,
        open_positions: list[dict[str, Any]],
        today_realized_loss: float = 0.0,
        current_equity: float | None = None,
        sector_lookup: dict[str, str] | None = None,
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
            prior_hwm = self._high_water_mark
            prior_halted = self._halted
            self._high_water_mark = max(self._high_water_mark, current_equity)
            drawdown = (self._high_water_mark - current_equity) / self._high_water_mark
            if drawdown >= self.drawdown_limit_pct:
                self._halted = True
            # Save state only if it changed
            if self._state_path is not None and (self._high_water_mark != prior_hwm or self._halted != prior_halted):
                from equities.risk.state import save_kernel_state
                save_kernel_state(self._state_path, self._high_water_mark, self._halted, self.capital)
            if drawdown >= self.drawdown_limit_pct:
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

        # --- Sector concentration cap ---
        if sector_lookup is not None:
            new_sector = sector_lookup.get(ticker, "")
            if new_sector:
                sector_exposure = sum(
                    p.get("shares", 0) * p.get("entry_price", 0)
                    for p in swing_open
                    if p.get("sector", "") == new_sector
                )
                if sector_exposure / self.capital >= self.max_sector_pct:
                    return SizedRecommendation(
                        recommendation, 0.0, False,
                        f"sector_concentration_{new_sector}_at_{self.max_sector_pct:.0%}_limit",
                    )

        # --- Return-correlation concentration cap ---
        # Catches same-bet exposure sector labels miss (e.g. semis spanning
        # multiple GICS sub-industries). Degrades silently to no-op when the
        # checker is absent or the candidate's price history is unavailable —
        # missing correlation data must not block or wave through a trade.
        if self._correlation_checker is not None:
            open_tickers = [str(p.get("ticker", "")) for p in swing_open]
            result = self._correlation_checker.evaluate(ticker, open_tickers)
            if result.available:
                worst = result.max_pairwise
                if worst is not None and worst[1] >= self.max_pairwise_corr:
                    peer, corr = worst
                    return SizedRecommendation(
                        recommendation, 0.0, False,
                        f"correlation_pairwise_{peer}_{corr:.2f}_at_{self.max_pairwise_corr:.0%}_limit",
                    )
                avg = result.portfolio_avg
                if avg is not None and avg >= self.max_portfolio_corr:
                    return SizedRecommendation(
                        recommendation, 0.0, False,
                        f"correlation_portfolio_avg_{avg:.2f}_at_{self.max_portfolio_corr:.0%}_limit",
                    )

        # --- Gap-aware sizing (swing) ---
        if recommendation.stop_loss is None or recommendation.entry is None:
            return SizedRecommendation(recommendation, 0.0, False, "missing_stop_or_entry")

        take_profit = getattr(recommendation, "take_profit", None)

        # --- Minimum reward:risk asymmetry gate ---
        if self.min_rr > 0 and take_profit is not None:
            risk = recommendation.entry - recommendation.stop_loss
            reward = take_profit - recommendation.entry
            if risk > 0:
                rr = reward / risk
                if rr < self.min_rr:
                    return SizedRecommendation(
                        recommendation, 0.0, False,
                        f"rr_{rr:.2f}_below_min_{self.min_rr:.1f}",
                    )

        # Build-tier / challenger sizing finally binds: scale risk by the
        # analyst chain's size_pct relative to the 2% GRADUAL_BUILD baseline.
        # Clamped so a bad size_pct can never 10x risk or zero it silently.
        size_pct = getattr(recommendation, "size_pct", 0.0) or 0.0
        if size_pct > 0:
            scale = max(0.25, min(2.0, size_pct / 0.02))
            effective_risk_pct = self.risk_pct * scale
        else:
            effective_risk_pct = self.risk_pct

        # Empirical Kelly: replaces flat risk only when this confidence band
        # has enough closed trades to estimate p honestly (>= kelly_min_trades).
        if self.kelly_fraction > 0 and self._win_stats_lookup is not None:
            try:
                n, win_rate = self._win_stats_lookup(recommendation.confidence)
            except Exception:
                n, win_rate = 0, 0.0
            if (
                n >= self.kelly_min_trades
                and take_profit is not None
                and recommendation.entry > recommendation.stop_loss
            ):
                b = (take_profit - recommendation.entry) / (
                    recommendation.entry - recommendation.stop_loss
                )
                kelly = empirical_kelly_risk_pct(win_rate, b, self.kelly_fraction)
                if kelly is not None:
                    effective_risk_pct = min(kelly, 2.0 * self.risk_pct)
                else:
                    # measured edge <= 0 in this band: floor to NIBBLE-scale risk
                    effective_risk_pct = min(effective_risk_pct, 0.5 * self.risk_pct)

        shares = size_shares(
            capital=self.capital,
            risk_pct=effective_risk_pct,
            entry=recommendation.entry,
            stop_loss=recommendation.stop_loss,
            gap_pct=self.gap_pct,
        )

        if not math.isfinite(shares) or shares <= 0:
            return SizedRecommendation(recommendation, 0.0, False, "zero_shares_after_sizing")

        # --- Max position size cap ---
        max_position_usd = self.max_name_pct * self.capital
        if shares * recommendation.entry > max_position_usd:
            shares = max_position_usd / recommendation.entry

        return SizedRecommendation(recommendation, round(shares, 6), True)
