from __future__ import annotations


def brier_score(pairs: list[tuple[float, bool]]) -> float:
    """Mean squared error between predicted probabilities and binary outcomes.

    Brier score = (1/N) * sum((p_i - o_i)^2), where o_i in {0, 1}.
    Perfect = 0.0, worst = 1.0, random (p=0.5) = 0.25.
    """
    if not pairs:
        raise ValueError("pairs must not be empty")
    total = sum((p - (1.0 if o else 0.0)) ** 2 for p, o in pairs)
    return total / len(pairs)


def calibration_buckets(
    pairs: list[tuple[float, bool]],
    n_buckets: int = 10,
) -> list[dict]:
    """Bin predictions by predicted probability; compute actual hit rate per bin.

    Returns list of {"predicted": float, "actual": float, "count": int},
    skipping empty buckets. Used to check whether p=0.7 really resolves ~70% of
    the time (calibration plot data).
    """
    width = 1.0 / n_buckets
    bins: dict[int, list[bool]] = {}
    for p, o in pairs:
        idx = min(int(p / width), n_buckets - 1)
        bins.setdefault(idx, []).append(o)

    result = []
    for idx in sorted(bins):
        outcomes = bins[idx]
        mid = (idx + 0.5) * width
        actual = sum(outcomes) / len(outcomes)
        result.append({"predicted": round(mid, 3), "actual": round(actual, 4), "count": len(outcomes)})
    return result
