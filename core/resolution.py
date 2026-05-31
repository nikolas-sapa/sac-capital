"""Resolution poller: parse gamma market settlement and close open positions.

Public API
----------
parse_resolution(item)         — pure parser, no I/O
fetch_resolution(condition_id) — live gamma API call (geo-blocked in dev)
resolve_open_positions(ledger, fetch_fn) — async loop over ledger open positions
"""
from __future__ import annotations

from typing import Awaitable, Callable

import httpx

from core.clob._gamma import maybe_parse_json_field as _maybe_parse
from core.ledger import Ledger

_GAMMA_BASE = "https://gamma-api.polymarket.com"
_WIN_THRESHOLD = 0.99


# ---------------------------------------------------------------------------
# Pure parser
# ---------------------------------------------------------------------------

def parse_resolution(item: dict) -> str | None:
    """Given a gamma market JSON dict, return the WINNING clob token_id if the
    market is resolved/closed, else None.

    Resolution semantics: a resolved Polymarket binary market has closed==true
    and outcomePrices settled to '1'/'0' — the winning outcome's price is 1.0.
    Returns the clobTokenId at the index whose outcomePrice >= 0.99.
    If not closed, or no price is ~1.0, returns None.

    Handles the JSON-encoded-string fields (outcomePrices, clobTokenIds) the
    same way core/clob/rest.py does (json.loads if str).
    """
    if not item.get("closed", False):
        return None

    prices = _maybe_parse(item.get("outcomePrices", []))
    clob_ids = _maybe_parse(item.get("clobTokenIds", []))

    for idx, price_str in enumerate(prices):
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            continue
        if price >= _WIN_THRESHOLD:
            if idx < len(clob_ids):
                return str(clob_ids[idx])

    return None


# ---------------------------------------------------------------------------
# Async network fetch (live path — geo-blocked in dev, tested via mock)
# ---------------------------------------------------------------------------

async def fetch_resolution(condition_id: str) -> str | None:
    """Hit gamma-api for this condition_id, parse via parse_resolution.

    Returns the winning clob token_id, or None if the market is not yet settled.
    This is the live network path; it is geo-blocked in the dev environment and
    is not covered by unit tests (tests inject a mock fetch_fn instead).
    """
    params = {"condition_ids": condition_id}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{_GAMMA_BASE}/markets", params=params)
        response.raise_for_status()
        data = response.json()

    if not data:
        return None

    return parse_resolution(data[0])


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

async def resolve_open_positions(
    ledger: Ledger,
    fetch_fn: Callable[[str], Awaitable[str | None]],
) -> int:
    """For each DISTINCT condition_id among ledger.open_positions():
    await fetch_fn(condition_id). If it returns a winning_token_id (not None):
    call ledger.resolve(condition_id, winning_token_id) and accumulate resolved
    row count. If None: leave that condition's positions untouched.

    Returns total rows resolved across all conditions.
    Dedupes condition_ids so fetch_fn is called once per condition.
    """
    positions = ledger.open_positions()
    if not positions:
        return 0

    # Dedupe — preserve insertion order for determinism
    seen: dict[str, None] = {}
    for pos in positions:
        seen[pos["condition_id"]] = None
    distinct_conditions = list(seen)

    total_resolved = 0
    for condition_id in distinct_conditions:
        winning_id = await fetch_fn(condition_id)
        if winning_id is not None:
            total_resolved += ledger.resolve(condition_id, winning_id)

    return total_resolved


# ---------------------------------------------------------------------------
# CLI entrypoint (invoked by launchd: uv run python -m core.resolution)
# ---------------------------------------------------------------------------

async def _main() -> None:
    from core.config import load_config
    from core.ledger import Ledger
    settings = load_config()
    ledger = Ledger("data/ledger.db")
    n = await resolve_open_positions(ledger, fetch_resolution)
    print(f"Resolved {n} position(s). Total realized PnL: {ledger.pnl():.2f}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
