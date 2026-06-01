from __future__ import annotations

from dataclasses import dataclass

_MAX_SPREAD = 3.0
_TIGHT_PAIR_THRESHOLD = 1.0


@dataclass(frozen=True)
class ConsensusResult:
    center: float       # best estimate of the true daily max
    spread: float       # full range across all three models
    outlier: str | None # "icon" | "gfs" | "ecmwf" | None
    outlier_above: bool # True if outlier is above center (upward skew)


def consensus(icon: float, gfs: float, ecmwf: float) -> ConsensusResult | None:
    """Return consensus or None when models disagree too much (spread > 3°)."""
    models = {"icon": icon, "gfs": gfs, "ecmwf": ecmwf}
    vals = list(models.values())
    spread = max(vals) - min(vals)

    if spread > _MAX_SPREAD:
        return None

    # Find the tightest pair; if within TIGHT_PAIR_THRESHOLD use their mean
    names = list(models.keys())
    pairs = [
        (names[0], names[1], abs(icon - gfs)),
        (names[0], names[2], abs(icon - ecmwf)),
        (names[1], names[2], abs(gfs - ecmwf)),
    ]
    pairs.sort(key=lambda x: x[2])
    a_name, b_name, pair_spread = pairs[0]

    overall_spread = max(vals) - min(vals)
    if overall_spread <= _TIGHT_PAIR_THRESHOLD:
        # All three agree — use mean of all, no outlier
        center = sum(vals) / 3
        outlier_name = None
    elif pair_spread <= _TIGHT_PAIR_THRESHOLD:
        # Two agree tightly; third is the outlier
        center = (models[a_name] + models[b_name]) / 2
        outlier_name = next(n for n in names if n not in (a_name, b_name))
    else:
        center = sum(vals) / 3
        outlier_name = None

    outlier_val = models[outlier_name] if outlier_name else center
    outlier_above = outlier_val > center if outlier_name else False

    return ConsensusResult(
        center=center,
        spread=spread,
        outlier=outlier_name,
        outlier_above=outlier_above,
    )
