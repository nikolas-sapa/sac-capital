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


import json
import re
from datetime import date, datetime

_WEEK = 7
_MONTH = 30


def _horizon_days(text: str | None, default: int = 21) -> int:
    """Parse an analyst horizon string ("1-2 weeks", "10 days", "3 months") to days.

    Takes the UPPER bound of a range — the time stop is a backstop, not a target.
    """
    if not text:
        return default
    m = re.search(r"(\d+)\s*(?:-\s*(\d+))?\s*(day|week|month)", text.lower())
    if not m:
        return default
    n = int(m.group(2) or m.group(1))
    unit = m.group(3)
    if unit == "day":
        return n
    if unit == "week":
        return n * _WEEK
    return n * _MONTH


def evaluate_exit(
    position: dict,
    current_price: float,
    today: date,
    trail_r: float = 1.5,
    default_horizon_days: int = 21,
) -> ExitSignal | None:
    """Stateless nightly exit evaluation for swing positions.

    Effective stop = max of:
      - the original hard stop
      - entry (breakeven) once high-water >= entry + 1R
      - high_water - trail_r * R once high-water >= take_profit (trail mode;
        take_profit is an ACTIVATOR, not an exit — winners run)
    Plus a horizon-aware time stop (upper bound of the analyst's horizon).

    CORE positions (no stop) are never exited here.
    """
    entry = position.get("entry_price")
    stop = position.get("stop_loss")
    target = position.get("take_profit")
    pos_id = position["id"]

    if stop is not None and entry is not None and entry > stop:
        r = entry - stop
        hw = position.get("high_water_price") or entry
        effective_stop = stop
        if hw >= entry + r:
            effective_stop = max(effective_stop, entry)  # breakeven ratchet at +1R
        if target is not None and hw >= target:
            effective_stop = max(effective_stop, hw - trail_r * r)  # trail mode
        if current_price <= effective_stop:
            reason = "stop_hit" if effective_stop == stop else "trailing_stop_hit"
            return ExitSignal(position_id=pos_id, reason=reason, exit_price=current_price)

        # Horizon time stop — swing only (requires a stop to identify the sleeve).
        opened_raw = position.get("opened_at") or ""
        try:
            opened = datetime.fromisoformat(opened_raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None
        try:
            horizon = json.loads(position.get("analysis_json") or "{}").get("horizon")
        except (TypeError, ValueError):
            horizon = None
        if (today - opened).days > _horizon_days(horizon, default_horizon_days):
            return ExitSignal(position_id=pos_id, reason="time_stop", exit_price=current_price)

    return None
