"""Gamma API market metadata client.

Provides:
  - parse_market(item) — pure parser: dict → Market (no I/O, testable offline)
  - fetch_markets(limit, active) — async fetcher via httpx

NOTE on price fields
--------------------
The gamma REST endpoint returns per-outcome mid prices via ``outcomePrices``
(the last-traded/mid price from the order book snapshot). True per-outcome
bid/ask are only available from the CLOB websocket (Task 7). Until then,
``best_bid = best_ask = outcomePrice`` for each outcome is the correct
mid-price fallback — it is NOT a fabrication.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from core.clob._gamma import maybe_parse_json_field as _maybe_parse
from core.markets import Market, Outcome

_GAMMA_BASE = "https://gamma-api.polymarket.com"


def _parse_utc(iso_str: str) -> datetime:
    """Parse an ISO-8601 string (with optional trailing 'Z') to a UTC datetime."""
    # datetime.fromisoformat in Python 3.11+ handles 'Z', but 3.12 still
    # doesn't in all cases — replace explicitly for safety.
    normalised = iso_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalised)
    # Ensure tzinfo is exactly timezone.utc (fromisoformat may return a
    # fixed-offset object equal to UTC but not *is* timezone.utc).
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_market(item: dict) -> Market:
    """Map a single gamma API market dict to a ``Market`` domain object.

    Handles JSON-encoded string fields (outcomes, outcomePrices, clobTokenIds)
    and uses per-outcome outcomePrices as mid-price fallback for best_bid/best_ask.
    """
    condition_id: str = item["conditionId"]
    question: str = item["question"]
    closed: bool = bool(item.get("closed", False))
    end_date: datetime = _parse_utc(item["endDate"])

    labels = _maybe_parse(item.get("outcomes", []))
    prices = _maybe_parse(item.get("outcomePrices", []))
    token_ids = _maybe_parse(item.get("clobTokenIds", []))

    # Pad shorter lists with defaults so zip always produces an Outcome per label.
    n = len(labels)
    prices = list(prices) + ["0.0"] * (n - len(prices))
    token_ids = list(token_ids) + [""] * (n - len(token_ids))

    outcomes: list[Outcome] = []
    for label, token_id, price_str in zip(labels, token_ids, prices):
        mid = float(price_str)
        outcomes.append(Outcome(
            token_id=str(token_id),
            label=str(label),
            best_bid=mid,   # mid-price fallback; per-outcome bid/ask from WS in Task 7
            best_ask=mid,
        ))

    return Market(
        condition_id=condition_id,
        question=question,
        outcomes=outcomes,
        end_date=end_date,
        closed=closed,
    )


# ---------------------------------------------------------------------------
# Async fetcher
# ---------------------------------------------------------------------------

async def fetch_markets(limit: int = 20, active: bool = True) -> list[Market]:
    """Fetch market metadata from the gamma REST API.

    Args:
        limit: Maximum number of markets to return.
        active: When True, request only active (unresolved) markets.

    Returns:
        A list of ``Market`` objects parsed from the API response.
    """
    params: dict[str, Any] = {"limit": limit, "active": str(active).lower()}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{_GAMMA_BASE}/markets", params=params)
        response.raise_for_status()
        return [parse_market(item) for item in response.json()]
