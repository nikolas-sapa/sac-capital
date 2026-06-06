"""07d — Equity paper tracker.

Nightly mark-to-market: updates unrealized PnL for open positions and fires
exit triggers (stop / target / time-stop). Plugs into EquityLedger + PriceFeed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from equities.ledger_equity import EquityLedger
from equities.risk.exits import ExitSignal, check_exit
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
        time_stop_days: Days before a position is time-stopped (default 21).
    """

    def __init__(
        self,
        ledger: EquityLedger,
        prices: Any,
        time_stop_days: int = 21,
    ) -> None:
        self._ledger = ledger
        self._prices = prices
        self._time_stop_days = time_stop_days

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
            if price is None:
                continue

            # Update mark price
            self._ledger.mark(ticker, price)

            # Check exit conditions
            opened_at = datetime.fromisoformat(pos["opened_at"])
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=timezone.utc)

            signal = check_exit(
                position_id=pos["id"],
                current_price=price,
                stop_loss=pos.get("stop_loss"),
                take_profit=pos.get("take_profit"),
                opened_at=opened_at,
                current_time=now,
                max_days=self._time_stop_days,
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
