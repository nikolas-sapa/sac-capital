"""07d — Equity paper tracker.

Nightly mark-to-market: updates unrealized PnL for open positions and fires
exit triggers (stop / target). Plugs into EquityLedger + PriceFeed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from equities.ledger_equity import EquityLedger
from equities.risk.exits import ExitSignal, check_exit, evaluate_exit
from equities.strategy import Recommendation, Sleeve


@dataclass(frozen=True)
class PaperFill:
    position_id: int
    ticker: str
    shares: float
    entry_price: float
    sleeve: str
    mode: str = "paper"


class EquityPaperTracker:
    """Open positions and run nightly mark + exit cycle against the EquityLedger.

    Args:
        ledger:    EquityLedger instance.
        prices:    Price provider; must have `latest_close(ticker) -> float | None`.
    """

    def __init__(
        self,
        ledger: EquityLedger,
        prices: Any,
        price_fallback: Callable[[str], float | None] | None = None,
        trail_r: float = 1.5,
    ) -> None:
        self._ledger = ledger
        self._prices = prices
        self._price_fallback = price_fallback
        self._trail_r = trail_r

    def open_position(
        self,
        recommendation: Recommendation,
        shares: float,
        fill_price: float,
        strategy: str = "",
    ) -> PaperFill:
        """Record a new paper fill in the ledger."""
        now = datetime.now(tz=timezone.utc)
        pos_id = self._ledger.open_position(
            recommendation, shares, fill_price, now, mode="paper", strategy=strategy
        )
        return PaperFill(
            position_id=pos_id,
            ticker=recommendation.instrument.ticker,
            shares=shares,
            entry_price=fill_price,
            sleeve=recommendation.sleeve.value,
        )

    def mark_and_check_exits(self) -> list[ExitSignal]:
        """Mark all open positions to current prices and fire any exit triggers.

        Returns the list of ExitSignals that were fired (and executed).
        """
        now = datetime.now(tz=timezone.utc)
        positions = self._ledger.open_positions()
        fired: list[ExitSignal] = []

        for pos in positions:
            if pos.get("status") == "submitted":
                continue
            ticker = pos["ticker"]
            price = self._prices.latest_close(ticker)
            if price is None and self._price_fallback is not None:
                price = self._price_fallback(ticker)
            if price is None:
                continue

            # Update mark price + high-water first so tonight's high counts
            self._ledger.mark(ticker, price)
            hw = max(
                pos.get("high_water_price") or pos.get("entry_price") or price,
                price,
            )

            signal = evaluate_exit(
                {**pos, "high_water_price": hw},
                current_price=price,
                today=now.date(),
                trail_r=self._trail_r,
            )

            if signal is not None:
                self._ledger.close_position(
                    position_id=signal.position_id,
                    exit_price=signal.exit_price,
                    exit_reason=signal.reason,
                    closed_at=now,
                )
                fired.append(signal)

        return fired
