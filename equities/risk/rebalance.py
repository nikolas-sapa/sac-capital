"""Enforce the per-name concentration cap on positions already held.

The risk kernel caps concentration at entry only — nothing in the system
reduces a position that has drifted past the limit, whether by price
appreciation or by repeated DCA adds. That makes the cap one-sided: it can be
breached and then never corrected.

This module computes the trims needed to bring over-weight names back to the
cap. It is deliberately conservative:

  * only names strictly above cap + band are touched (band prevents churn on
    trivial drift)
  * a position is trimmed TO the cap, never below it
  * a position is never closed outright — this enforces sizing, it does not
    express a view on the stock
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Trim:
    ticker: str
    shares: float          # shares to sell (positive)
    current_weight: float  # weight before the trim, as a fraction of equity
    target_weight: float   # weight after the trim
    notional: float        # approximate USD raised

    @property
    def evidence(self) -> str:
        return (
            f"{self.ticker}: {self.current_weight:.1%} -> {self.target_weight:.1%} "
            f"(sell {self.shares:.4f} sh, ~${self.notional:,.0f})"
        )


# A cap below this is treated as misconfiguration rather than intent: trimming
# to it would liquidate the book. Refuse instead of obeying blindly.
_MIN_PLAUSIBLE_CAP = 0.05
# Never sell more than this share of a position in one run. A genuinely large
# overweight converges over several runs instead of dumping in one order.
_MAX_TRIM_FRACTION = 0.5


def compute_trims(
    positions: list[dict],
    equity: float,
    max_name_pct: float,
    band: float = 0.01,
    min_notional: float = 1.0,
) -> list[Trim]:
    """Return the trims that bring over-weight names back to `max_name_pct`.

    Args:
        positions:     dicts with 'ticker', 'market_value' and 'shares'.
        equity:        total account equity.
        max_name_pct:  per-name ceiling as a fraction (0.25 = 25%).
        band:          only act once weight exceeds cap + band, so a name
                       sitting a hair over does not churn every run.
        min_notional:  skip trims below this USD value — not worth an order.

    Positions are aggregated by ticker first: the same name held across sleeves
    is one concentration risk, matching the kernel's entry-side behaviour.
    """
    if equity <= 0 or max_name_pct < _MIN_PLAUSIBLE_CAP:
        return []

    by_ticker: dict[str, dict[str, float]] = {}
    for p in positions:
        ticker = str(p.get("ticker") or p.get("symbol") or "").upper()
        if not ticker:
            continue
        mv = float(p.get("market_value") or 0.0)
        shares = float(p.get("shares") or p.get("qty") or 0.0)
        if mv <= 0 or shares <= 0:
            continue  # ignore shorts/empties; this cap is for long concentration
        agg = by_ticker.setdefault(ticker, {"market_value": 0.0, "shares": 0.0})
        agg["market_value"] += mv
        agg["shares"] += shares

    trims: list[Trim] = []
    for ticker, agg in sorted(by_ticker.items()):
        mv, shares = agg["market_value"], agg["shares"]
        weight = mv / equity
        if weight <= max_name_pct + band:
            continue

        target_mv = max_name_pct * equity
        excess_mv = mv - target_mv
        if excess_mv < min_notional:
            continue

        price = mv / shares
        sell_shares = min(excess_mv / price, shares * _MAX_TRIM_FRACTION)
        if sell_shares <= 0:
            continue

        sell_shares = round(sell_shares, 6)
        realised = sell_shares * price
        if realised < min_notional:
            continue

        trims.append(
            Trim(
                ticker=ticker,
                shares=sell_shares,
                current_weight=weight,
                # Report where this trim actually lands, which is the cap in
                # the normal case and short of it when the clamp bites.
                target_weight=(mv - realised) / equity,
                notional=realised,
            )
        )
    return trims
