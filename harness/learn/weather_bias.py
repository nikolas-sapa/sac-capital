from __future__ import annotations

from typing import Sequence


def learn_bias(
    samples: Sequence[tuple[float, float]],
    min_n: int = 20,
    max_step: float = 0.5,
) -> float:
    """Return a bounded temperature bias correction for a single station.

    samples: list of (forecast_temp, actual_temp)
    Returns the mean (actual - forecast) error, capped to ±max_step.
    Returns 0.0 when fewer than min_n samples are available.
    """
    if len(samples) < min_n:
        return 0.0

    errors = [actual - forecast for forecast, actual in samples]
    mean_bias = sum(errors) / len(errors)
    return max(-max_step, min(max_step, mean_bias))
