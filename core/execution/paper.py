"""Paper (simulated) executor for Polymarket bot.

PaperExecutor implements the Executor protocol using in-memory simulation —
no real orders are placed; fills are recorded straight to the Ledger.

WHY fee folds into shares (not a separate field):
  The Fill dataclass has no fee field by design. Rather than tracking fees
  separately, the cost is represented as fewer shares purchased for the same
  stake. On a winning trade pnl = shares - stake, so reducing shares by
  (1 - fee_rate) correctly shrinks the net payout. On a loss pnl = -stake,
  which is unchanged. This gives realistic net-of-cost paper pnl without any
  extra schema changes to Fill or Ledger.

Default parameters:
  slippage=0.01  — 1% conservative estimate for thin/illiquid markets, the
                   typical target for an LLM-driven bot.
  fee_rate=0.0   — Polymarket's base orderbook charges no maker fee; override
                   to stress-test costs (e.g. fee_rate=0.02 for taker fills).
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.execution.base import Fill
from core.ledger import Ledger
from core.strategy import Signal


class PaperExecutor:
    """Simulated executor: applies slippage + fee model, records Fill to Ledger.

    Implements the Executor protocol (place(signal, stake) -> Fill).
    """

    def __init__(
        self,
        ledger: Ledger,
        slippage: float = 0.01,
        fee_rate: float = 0.0,
    ) -> None:
        self._ledger = ledger
        self._slippage = slippage
        self._fee_rate = fee_rate

    def place(self, signal: Signal, stake: float, strategy: str = "") -> Fill:
        """Simulate a buy order and record it in the ledger.

        Execution price is worsened by slippage (crossing the spread on thin
        markets), then capped at 0.999 — prices are probabilities in (0, 1).

        Fee is folded into shares: buying fewer shares for the same stake
        captures the cost without a dedicated fee field on Fill.
        """
        # Worsen price by slippage; cap below 1.0 (prices are probabilities)
        exec_price = min(signal.price * (1 + self._slippage), 0.999)

        # Fold fee into shares so pnl is net-of-cost automatically
        gross_shares = stake / exec_price
        shares = gross_shares * (1 - self._fee_rate)

        fill = Fill(
            signal=signal,
            stake=stake,
            shares=shares,
            avg_price=exec_price,
            timestamp=datetime.now(timezone.utc),
            mode="paper",
        )
        self._ledger.record(fill, strategy=strategy)
        return fill
