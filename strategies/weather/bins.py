from __future__ import annotations

from core.markets import Market, Outcome
from strategies.weather.consensus import ConsensusResult


def _parse_bin_midpoint(label: str) -> float | None:
    """Extract numeric temperature from a bin label like '70°' or '70.0'."""
    cleaned = label.replace("°", "").replace("F", "").replace("C", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def find_bin(market: Market, temp: float) -> str | None:
    """Return the token_id of the bin closest to temp; None if no parseable bins."""
    candidates: list[tuple[float, str]] = []
    for o in market.outcomes:
        mid = _parse_bin_midpoint(o.label)
        if mid is not None:
            candidates.append((mid, o.token_id))
    if not candidates:
        return None
    # Nearest midpoint (gap fallback)
    return min(candidates, key=lambda x: abs(x[0] - temp))[1]


def build_portfolio(cr: ConsensusResult, market: Market) -> list[Outcome]:
    """Return 3 adjacent outcomes: center ± 1, with upward skew when outlier is above."""
    outcomes_with_mid: list[tuple[float, Outcome]] = []
    for o in market.outcomes:
        mid = _parse_bin_midpoint(o.label)
        if mid is not None:
            outcomes_with_mid.append((mid, o))
    if not outcomes_with_mid:
        return []

    outcomes_with_mid.sort(key=lambda x: x[0])
    mids = [m for m, _ in outcomes_with_mid]

    # Find center bin index
    center_idx = min(range(len(mids)), key=lambda i: abs(mids[i] - cr.center))

    if cr.outlier is not None and cr.outlier_above:
        # Upward skew: center, center-1, center+1... but prefer center+1 over center-2
        indices = [center_idx - 1, center_idx, center_idx + 1]
    else:
        # Symmetric: center-1, center, center+1
        indices = [center_idx - 1, center_idx, center_idx + 1]

    selected = [outcomes_with_mid[i][1] for i in indices if 0 <= i < len(outcomes_with_mid)]
    return selected
