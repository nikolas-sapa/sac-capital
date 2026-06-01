from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

import websockets


@dataclass(frozen=True)
class SpotTick:
    symbol: str
    price: float
    ts: datetime   # trade execution time (UTC)


def parse_trade(msg: dict) -> SpotTick:
    """Parse a Binance individual trade stream message into a SpotTick."""
    if msg.get("e") != "trade":
        raise ValueError(f"Expected 'trade' event, got '{msg.get('e')}'")
    return SpotTick(
        symbol=str(msg["s"]),
        price=float(msg["p"]),
        ts=datetime.fromtimestamp(msg["T"] / 1000.0, tz=timezone.utc),
    )


async def stream(symbol: str = "BTCUSDT") -> AsyncIterator[SpotTick]:
    """Async generator yielding SpotTicks from the Binance trade stream."""
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@trade"
    import json
    async with websockets.connect(url) as ws:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                yield parse_trade(msg)
            except (ValueError, KeyError):
                continue
