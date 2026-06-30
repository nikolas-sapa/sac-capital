"""07d — Exit trigger logic for swing positions.

Two exit types:
- STOP_HIT: current_price ≤ stop_loss (hard stop)
- TARGET_HIT: current_price ≥ take_profit
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitSignal:
    position_id: int
    reason: str       # "stop_hit" | "target_hit"
    exit_price: float


def check_exit(
    position_id: int,
    current_price: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> ExitSignal | None:
    """Return an ExitSignal if any exit condition is triggered, else None.

    Args:
        position_id:   DB row id of the position.
        current_price: Latest mark price.
        stop_loss:     Stop price (None for CORE/DCA positions).
        take_profit:   Target price (None for CORE/DCA positions).
    """
    if stop_loss is not None and current_price <= stop_loss:
        return ExitSignal(
            position_id=position_id,
            reason="stop_hit",
            exit_price=current_price,  # gap fill handled upstream
        )

    if take_profit is not None and current_price >= take_profit:
        return ExitSignal(
            position_id=position_id,
            reason="target_hit",
            exit_price=current_price,
        )

    return None
