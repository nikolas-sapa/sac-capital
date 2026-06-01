"""07e — Revolut cost model for forward-paper kill-gate.

Revolut pricing (as of plan spec):
- 1 commission-free trade per month, then 0.25% per trade
- FX spread: negligible for USD equities (assumed zero)
- Stop orders become market orders when triggered → gap slippage

Round-trip cost per trade = entry_commission + exit_commission + gap_penalty
"""
from __future__ import annotations

_COMMISSION_PCT = 0.0025        # 0.25% per leg (post-free-trade)
_DEFAULT_GAP_PCT = 0.02         # 2% gap penalty on stop-exit fill


def entry_cost(entry_price: float, shares: float) -> float:
    """Commission on the entry leg."""
    return entry_price * shares * _COMMISSION_PCT


def exit_cost(
    exit_price: float,
    shares: float,
    is_gap_stop: bool = False,
    gap_pct: float = _DEFAULT_GAP_PCT,
) -> float:
    """Commission + gap penalty on the exit leg.

    When `is_gap_stop=True` (stop order hit on a gap), the actual fill price
    is modelled as `exit_price * (1 - gap_pct)`, not the stop price.
    """
    if is_gap_stop:
        actual_exit = exit_price * (1.0 - gap_pct)
    else:
        actual_exit = exit_price

    commission = actual_exit * shares * _COMMISSION_PCT
    gap_slippage = (exit_price - actual_exit) * shares if is_gap_stop else 0.0
    return commission + gap_slippage


def round_trip_cost(
    entry_price: float,
    exit_price: float,
    shares: float,
    is_gap_stop: bool = False,
    gap_pct: float = _DEFAULT_GAP_PCT,
) -> float:
    """Total round-trip cost (commissions + gap) in USD."""
    return entry_cost(entry_price, shares) + exit_cost(exit_price, shares, is_gap_stop, gap_pct)


def net_pnl(
    entry_price: float,
    exit_price: float,
    shares: float,
    is_gap_stop: bool = False,
    gap_pct: float = _DEFAULT_GAP_PCT,
) -> float:
    """Realized PnL after deducting round-trip costs."""
    gross = (exit_price - entry_price) * shares
    return gross - round_trip_cost(entry_price, exit_price, shares, is_gap_stop, gap_pct)
