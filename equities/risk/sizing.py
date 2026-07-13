"""07d — Gap-aware position sizing.

Shares = (capital * risk_pct) / stop_distance_gap_adjusted

The stop is a Revolut stop-order (becomes a market order when hit), so on a
gap the actual fill will be worse. We model a gap penalty of `gap_pct` as a
fraction of stop distance so the paper results don't lie. Default 2%.
"""
from __future__ import annotations

import math

_DEFAULT_GAP_PCT = 0.02  # assume stop fills 2% worse than the stop price on gaps


def size_shares(
    capital: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    gap_pct: float = _DEFAULT_GAP_PCT,
) -> float:
    """Return the number of shares to buy so max loss = risk_pct * capital.

    Args:
        capital:   Available capital (e.g. 1000.0 USD)
        risk_pct:  Max fractional loss acceptable (e.g. 0.02 = 2%)
        entry:     Limit-buy price
        stop_loss: Stop-order price (below entry for long)
        gap_pct:   Gap penalty: stop fills at stop_loss * (1 - gap_pct) on a bad gap

    Returns:
        Number of shares (float; Revolut supports fractional)
    """
    if not math.isfinite(entry) or not math.isfinite(stop_loss):
        raise ValueError(f"size_shares received non-finite value: entry={entry}, stop_loss={stop_loss}")
    if entry <= 0 or stop_loss <= 0 or entry <= stop_loss:
        return 0.0
    if not (0 < risk_pct <= 1):
        return 0.0

    gap_adjusted_stop = stop_loss * (1.0 - gap_pct)
    stop_distance = entry - gap_adjusted_stop

    if stop_distance <= 0:
        return 0.0

    max_loss_usd = capital * risk_pct
    return max_loss_usd / stop_distance


def empirical_kelly_risk_pct(
    win_rate: float,
    payoff_b: float,
    kelly_fraction: float,
    hard_cap: float = 0.5,
) -> float | None:
    """Fractional-Kelly risk (fraction of capital at the stop) from MEASURED stats.

    f* = (b*p - q) / b. Returns None when the measured edge is non-positive —
    Kelly of a negative edge is a short position in your own strategy.
    kelly_fraction is hard-capped: growth is zero at 2x Kelly and estimation
    error makes intended-full-Kelly an overbet, so >hard_cap is never honored.
    """
    if payoff_b <= 0 or not (0.0 <= win_rate <= 1.0):
        return None
    q = 1.0 - win_rate
    f_star = (payoff_b * win_rate - q) / payoff_b
    if f_star <= 0:
        return None
    return min(kelly_fraction, hard_cap) * f_star
