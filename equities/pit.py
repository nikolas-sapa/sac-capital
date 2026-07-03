"""Point-in-time (look-ahead) guard for decision inputs.

Ensures signal sources provide data with timestamps not exceeding the decision
cutoff (run start time). Prevents accidental forward-looking bias.
"""
from __future__ import annotations

from datetime import datetime


class LookAheadError(Exception):
    """A signal source supplied data newer than the decision cutoff."""

    pass


def assert_point_in_time(cutoff_utc: str, sources: list[dict]) -> list[str]:
    """Raise LookAheadError if any source's as_of_utc exceeds cutoff_utc.

    Sources with as_of_utc=None are skipped and returned as warnings (caller logs).
    ISO-8601 string comparison after parsing with datetime.fromisoformat.
    Handles trailing 'Z' by replacing with '+00:00'.

    Args:
        cutoff_utc: ISO-8601 decision cutoff (e.g., "2026-07-03T12:00:00Z")
        sources: List of dicts with "name" and optional "as_of_utc" keys

    Returns:
        List of source names lacking timestamps (caller logs a warning)

    Raises:
        LookAheadError: If any source's as_of_utc exceeds cutoff_utc
    """
    # Normalize cutoff
    cutoff_str = cutoff_utc.replace("Z", "+00:00")
    cutoff_dt = datetime.fromisoformat(cutoff_str)

    warnings: list[str] = []

    for source in sources:
        name = source.get("name", "unknown")
        as_of = source.get("as_of_utc")

        # Missing or None timestamp: warn, don't fail
        if as_of is None:
            warnings.append(name)
            continue

        # Normalize timestamp
        as_of_str = as_of.replace("Z", "+00:00")
        as_of_dt = datetime.fromisoformat(as_of_str)

        # Check for look-ahead: as_of must not exceed cutoff
        if as_of_dt > cutoff_dt:
            raise LookAheadError(
                f"Source '{name}' data as_of {as_of} exceeds cutoff {cutoff_utc}"
            )

    return warnings
