from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


@dataclass
class Calibrator:
    """Wraps a fitted isotonic regression to correct raw predicted probabilities."""

    _model: Any  # sklearn IsotonicRegression

    def apply(self, raw_prob: float) -> float:
        """Map a raw predicted probability to a calibrated one."""
        return float(self._model.predict(np.array([raw_prob]))[0])


def fit_calibrator(
    samples: Sequence[tuple[float, int]],
    min_n: int = 50,
) -> Calibrator | None:
    """Fit an isotonic calibrator from (predicted_prob, outcome) pairs.

    Returns None if fewer than min_n samples are provided — prevents
    learning on noise when the sample set is too small.
    """
    if len(samples) < min_n:
        return None

    from sklearn.isotonic import IsotonicRegression

    probs = np.array([p for p, _ in samples])
    outcomes = np.array([o for _, o in samples], dtype=float)

    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(probs, outcomes)
    return Calibrator(_model=ir)
