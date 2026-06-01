from __future__ import annotations

from orchestrator.performance import RollingStats


def allocate(
    bankroll: float,
    stats: dict[str, RollingStats],
    floor_pct: float = 0.05,
    ceiling_pct: float = 0.50,
) -> dict[str, float]:
    """Split bankroll into per-strategy budgets.

    - Every enabled strategy gets at least floor_pct * bankroll.
    - No strategy gets more than ceiling_pct * bankroll.
    - Remaining budget above the floor is distributed proportional to expectancy.
    - New strategies with no track record (n_resolved == 0) get the floor only.
    - Negative-expectancy strategies get the floor only (exploration budget).
    """
    if not stats:
        return {}

    floor = floor_pct * bankroll
    ceiling = ceiling_pct * bankroll
    n = len(stats)

    # Guard: if even the floor exceeds bankroll, scale down evenly
    if n * floor > bankroll:
        per = bankroll / n
        return {name: per for name in stats}

    # Base: everyone gets the floor
    alloc = {name: floor for name in stats}
    remaining = bankroll - n * floor

    # Distribute remaining proportional to positive expectancy
    scores = {name: max(0.0, s.expectancy) for name, s in stats.items()}
    total_score = sum(scores.values())

    if total_score > 0 and remaining > 0:
        for name, score in scores.items():
            bonus = remaining * (score / total_score)
            alloc[name] = min(ceiling, alloc[name] + bonus)

    return alloc
