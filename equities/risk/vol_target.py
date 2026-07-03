"""Shadow vol-targeting sizing — A/B variant to fractional-Kelly kernel sizing.

Implements a vol-normalized allocation strategy as a non-destructive shadow side-channel
for decision-making analytics and A/B experimentation. Never affects execution.

Formula:
    raw_frac = target_vol_pct / vol_20d_ann_pct (ratio of target to current vol)
    frac = min(raw_frac * 0.02, max_alloc_pct)  (2% base scaled by vol ratio, hard cap)
    alloc_usd = capital * frac
    shares = alloc_usd / entry

This scales position size inversely with realized volatility:
- High vol → smaller fraction → fewer shares
- Low vol → larger fraction (capped) → more shares
- None/0/negative vol → None (no sizing data)
"""
from __future__ import annotations


def vol_target_shares(
    entry: float,
    vol_20d_ann_pct: float | None,
    capital: float,
    target_vol_pct: float = 20.0,
    max_alloc_pct: float = 0.25,
) -> float | None:
    """Compute shadow position size using vol-normalized allocation.

    Args:
        entry: Entry price (must be > 0).
        vol_20d_ann_pct: 20-day annualized volatility as a percentage (from technicals).
            May be None if insufficient price history. Must be > 0.
        capital: Available capital (USD).
        target_vol_pct: Target volatility percentage for the strategy (default 20%).
        max_alloc_pct: Hard cap on allocation fraction of capital (default 25%).

    Returns:
        Number of shares to buy (float; may be fractional).
        None if vol is None, <=0, or entry is <=0.

    Formula:
        raw_frac = target_vol_pct / vol_20d_ann_pct
        frac = min(raw_frac * 0.02, max_alloc_pct)
        alloc_usd = capital * frac
        shares = alloc_usd / entry
    """
    # Guard: invalid vol
    if vol_20d_ann_pct is None or vol_20d_ann_pct <= 0.0:
        return None

    # Guard: invalid entry
    if entry <= 0.0:
        return None

    # Compute vol-normalized fraction
    raw_frac = target_vol_pct / vol_20d_ann_pct
    # Apply 2% base scale and hard cap
    frac = min(raw_frac * 0.02, max_alloc_pct)

    # Convert to shares
    alloc_usd = capital * frac
    shares = alloc_usd / entry

    return shares
