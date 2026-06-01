from __future__ import annotations

from typing import Any, Callable, Sequence


def retune(
    param_grid: Sequence[Any],
    resolved_trades: Sequence[Any],
    validate_fn: Callable[[Sequence[Any], Any], float],
    max_step: float,
    current_value: float,
) -> float:
    """Walk-forward threshold re-tuner.

    Splits resolved_trades into a 60/40 train/validate window (sequential,
    never shuffled). Evaluates each candidate in param_grid on the validate
    window via validate_fn. Returns the best candidate, clamped to max_step
    distance from current_value.

    Candidates outside max_step are skipped entirely — we never jump far
    from the current value in a single cycle to prevent chasing noise.
    Returns current_value unchanged when fewer than 4 trades are available.
    """
    if len(resolved_trades) < 4:
        return current_value

    split = int(len(resolved_trades) * 0.6)
    validate = list(resolved_trades[split:])

    best_score: float | None = None
    best_value: float = current_value

    for candidate in param_grid:
        try:
            distance = abs(float(candidate) - current_value)
        except (TypeError, ValueError):
            continue

        if distance > max_step:
            continue

        score = validate_fn(validate, candidate)
        if best_score is None or score > best_score:
            best_score = score
            best_value = candidate

    return best_value
