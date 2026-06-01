from __future__ import annotations

from datetime import datetime, timezone

from core.markets import Market

_MIN_HOURS_TO_CLOSE = 6
_DEAD_ZONE_LOW = 0.05
_DEAD_ZONE_HIGH = 0.95


def is_candidate(market: Market, min_hours: float = _MIN_HOURS_TO_CLOSE) -> bool:
    """Return True if the market is worth sending to the LLM estimator."""
    if market.closed:
        return False

    hours_left = (market.end_date - datetime.now(tz=timezone.utc)).total_seconds() / 3600
    if hours_left < min_hours:
        return False

    # Need at least one outcome with a tradeable ask
    yes_outcomes = [o for o in market.outcomes if o.label.lower() == "yes"]
    if not yes_outcomes:
        return False
    yes = yes_outcomes[0]

    if yes.best_ask <= 0.0:
        return False

    if yes.best_ask < _DEAD_ZONE_LOW or yes.best_ask > _DEAD_ZONE_HIGH:
        return False

    return True


def liquidity_score(market: Market) -> float:
    """Score 0–1: tighter YES spread → higher score (thin-but-tradeable is fine)."""
    yes_outcomes = [o for o in market.outcomes if o.label.lower() == "yes"]
    if not yes_outcomes:
        return 0.0
    yes = yes_outcomes[0]
    if yes.best_ask <= 0.0:
        return 0.0
    spread = yes.best_ask - yes.best_bid
    # Map spread [0, 1] → score [1, 0]; clamp to [0, 1]
    return max(0.0, min(1.0, 1.0 - spread))


def candidate_markets(markets: list[Market]) -> list[Market]:
    """Filter to candidates and sort by liquidity score (tightest spread first)."""
    filtered = [m for m in markets if is_candidate(m)]
    return sorted(filtered, key=liquidity_score, reverse=True)
