"""07d — Exit trigger logic for swing positions.

Three exit types:
- STOP_HIT: current_price ≤ stop_loss (hard stop)
- TARGET_HIT: current_price ≥ take_profit
- TIME_STOP: position has been open ≥ max_days without hitting TP
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExitSignal:
    position_id: int
    reason: str       # "stop_hit" | "target_hit" | "time_stop"
    exit_price: float


def check_exit(
    position_id: int,
    current_price: float,
    stop_loss: float | None,
    take_profit: float | None,
    opened_at: datetime,
    current_time: datetime,
    max_days: int = 21,
) -> ExitSignal | None:
    """Return an ExitSignal if any exit condition is triggered, else None.

    Args:
        position_id:   DB row id of the position.
        current_price: Latest mark price.
        stop_loss:     Stop price (None for CORE/DCA positions).
        take_profit:   Target price (None for CORE/DCA positions).
        opened_at:     Position open timestamp.
        current_time:  Now (UTC).
        max_days:      Time-stop after this many days (default 21).
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

    days_open = (current_time - opened_at).total_seconds() / 86400
    if days_open >= max_days:
        return ExitSignal(
            position_id=position_id,
            reason="time_stop",
            exit_price=current_price,
        )

    return None
