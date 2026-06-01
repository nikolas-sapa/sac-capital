"""07f — Parameter variant generation.

A variant is a named set of strategy parameters. The harness generates small
perturbations of the current best params and evaluates them in a tournament.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(frozen=True)
class ParameterVariant:
    """A candidate parameter set to evaluate in the tournament."""

    name: str
    params: dict[str, Any]


def generate_variants(
    current: dict[str, Any],
    ranges: dict[str, Sequence[Any]],
    max_variants: int = 10,
) -> list[ParameterVariant]:
    """Generate candidate variants by perturbing one parameter at a time.

    For each parameter in `ranges`, create one variant per candidate value.
    The baseline (current params) is always included as the first variant.
    Total variants capped at `max_variants` (excluding baseline).

    Args:
        current:      Current "champion" parameter set.
        ranges:       Dict mapping param_name → list of candidate values.
        max_variants: Max number of challenger variants (not counting baseline).

    Returns:
        List of ParameterVariants starting with the baseline.
    """
    baseline = ParameterVariant(name="baseline", params=dict(current))
    variants = [baseline]

    count = 0
    for param_name, candidates in ranges.items():
        for value in candidates:
            if value == current.get(param_name):
                continue  # already the current value — skip
            if count >= max_variants:
                return variants
            new_params = dict(current)
            new_params[param_name] = value
            name = f"{param_name}={value}"
            variants.append(ParameterVariant(name=name, params=new_params))
            count += 1

    return variants
