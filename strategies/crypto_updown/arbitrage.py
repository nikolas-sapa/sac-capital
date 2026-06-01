from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArbSignal:
    ask_up: float
    ask_down: float
    fee_per_leg: float
    size_up: float    # units to buy of the Up token
    size_down: float  # units to buy of the Down token (== size_up)
    expected_profit_per_unit: float


def find_arb(
    ask_up: float,
    ask_down: float,
    fee_per_leg: float = 0.01,
    unit_size: float = 1.0,
) -> ArbSignal | None:
    """Return an ArbSignal if buying both legs costs less than the guaranteed $1 payout.

    In a binary Up/Down market exactly one outcome resolves YES → pays $1.
    Buying both Up and Down guarantees $1 regardless of outcome.
    Profit per unit = 1.0 - ask_up - ask_down - 2*fee_per_leg.
    Fee/slippage included so a 1% gross edge cannot become net-negative silently.
    """
    total_cost = ask_up + ask_down + 2 * fee_per_leg
    profit = 1.0 - total_cost

    if profit <= 0:
        return None

    return ArbSignal(
        ask_up=ask_up,
        ask_down=ask_down,
        fee_per_leg=fee_per_leg,
        size_up=unit_size,
        size_down=unit_size,
        expected_profit_per_unit=round(profit, 6),
    )
