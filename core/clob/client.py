"""Raw CLOB websocket client for Polymarket market-channel order book data.

This is the hot path. Uses the `websockets` library directly (no SDK wrapper)
for minimal overhead.

Deferred (Foundation scope — book snapshots only):
  - price_change events (incremental tick updates)
  - tick_size_change events
  - orderbook-diff merging / delta application
  - metrics / prometheus counters

Usage (geo-blocked on Greek IPs — requires VPN):
    uv run python -m core.clob.client <token_id>
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from typing import AsyncIterator

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

_WS_URL = "wss://ws-subscribe.clob.polymarket.com/ws/market"

# Reconnect backoff: start 1 s, double each attempt, cap at 30 s.
_BACKOFF_START = 1.0
_BACKOFF_CAP = 30.0


# ---------------------------------------------------------------------------
# Domain type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderBook:
    """Immutable snapshot of a Polymarket CLOB order book for one token."""

    asset_id: str
    bids: list[tuple[float, float]]   # (price, size), sorted DESCENDING by price (best first)
    asks: list[tuple[float, float]]   # (price, size), sorted ASCENDING by price (best first)
    best_bid: float                   # highest bid price; 0.0 if no bids
    best_ask: float                   # lowest ask price; 0.0 if no asks


# ---------------------------------------------------------------------------
# Pure parser
# ---------------------------------------------------------------------------


def _apply_book_message(msg: dict) -> OrderBook:
    """Parse a Polymarket CLOB market-channel ``book`` message into an OrderBook.

    Pure function — no I/O, safe to test offline.

    Expected message shape::

        {
            "event_type": "book",
            "asset_id": "<token_id>",
            "market": "<condition_id>",
            "bids": [{"price": "0.48", "size": "100"}, ...],
            "asks": [{"price": "0.52", "size": "200"}, ...],
            "timestamp": "...",
            "hash": "..."
        }

    Args:
        msg: Parsed JSON dict from the websocket.

    Returns:
        An immutable :class:`OrderBook` snapshot.
    """
    asset_id: str = msg["asset_id"]

    raw_bids: list[dict] = msg.get("bids") or []
    raw_asks: list[dict] = msg.get("asks") or []

    bids: list[tuple[float, float]] = sorted(
        [(float(b["price"]), float(b["size"])) for b in raw_bids],
        key=lambda t: t[0],
        reverse=True,  # descending: best (highest) bid first
    )
    asks: list[tuple[float, float]] = sorted(
        [(float(a["price"]), float(a["size"])) for a in raw_asks],
        key=lambda t: t[0],
        reverse=False,  # ascending: best (lowest) ask first
    )

    best_bid = bids[0][0] if bids else 0.0
    best_ask = asks[0][0] if asks else 0.0

    return OrderBook(
        asset_id=asset_id,
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
    )


# ---------------------------------------------------------------------------
# Websocket client
# ---------------------------------------------------------------------------


class ClobWebsocket:
    """Raw CLOB websocket client with automatic reconnection and backoff.

    Connects to the Polymarket CLOB market channel and yields :class:`OrderBook`
    snapshots for every ``book`` event received.

    Note: Only ``book`` (full snapshot) events are handled. ``price_change``
    and ``tick_size_change`` incremental events are deferred beyond Foundation
    scope — they are intentionally ignored here.
    """

    def __init__(self, url: str = _WS_URL) -> None:
        self._url = url

    async def stream(self, token_ids: list[str]) -> AsyncIterator[OrderBook]:
        """Yield OrderBook snapshots for the given token IDs.

        Implements automatic reconnection with exponential backoff. A
        successful message receipt resets the backoff counter.

        Args:
            token_ids: List of Polymarket token IDs to subscribe to.

        Yields:
            :class:`OrderBook` for each ``book`` event received.
        """
        subscribe_payload = json.dumps({"assets_ids": token_ids, "type": "market"})
        backoff = _BACKOFF_START

        # The `async for websocket in connect(...)` pattern (websockets v16)
        # handles reconnection on transient errors automatically with its own
        # exponential backoff. We layer our own backoff on top only for the
        # subscribe/recv failure path to avoid hammering on persistent errors.
        async for websocket in connect(self._url):
            try:
                await websocket.send(subscribe_payload)
                logger.info("Subscribed to CLOB market channel for %d token(s)", len(token_ids))

                async for raw in websocket:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Non-JSON message ignored: %.120s", raw)
                        continue

                    event_type = msg.get("event_type")

                    if event_type == "book":
                        # Reset backoff on successful message receipt.
                        backoff = _BACKOFF_START
                        yield _apply_book_message(msg)

                    # price_change / tick_size_change deferred — Foundation
                    # scope uses full book snapshots only.

            except ConnectionClosed as exc:
                logger.warning("CLOB websocket closed (%s); reconnecting in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_CAP)
                continue


# ---------------------------------------------------------------------------
# __main__ — manual hot-path check (geo-blocked on Greek IPs; requires VPN)
# ---------------------------------------------------------------------------
#
# Invocation:
#   uv run python -m core.clob.client <token_id>
#
# Expected output (~10 s of live top-of-book prints, e.g.):
#   [token-0x1a2b...] best_bid=0.4800  best_ask=0.5200
#   [token-0x1a2b...] best_bid=0.4800  best_ask=0.5150
#   ...
#   Done.
#
# STEP 5 STATUS: blocked pending VPN — Polymarket geo-blocks Greek IPs.
# Run from a non-blocked network or via VPN to validate live behaviour.

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("Usage: uv run python -m core.clob.client <token_id>", file=sys.stderr)
        sys.exit(1)

    token_id = sys.argv[1]

    async def _main() -> None:
        client = ClobWebsocket()
        deadline = asyncio.get_event_loop().time() + 10.0
        async for ob in client.stream([token_id]):
            print(f"[{ob.asset_id}] best_bid={ob.best_bid:.4f}  best_ask={ob.best_ask:.4f}")
            if asyncio.get_event_loop().time() >= deadline:
                break
        print("Done.")

    asyncio.run(_main())
