"""
Task 2 — LATENCY GATE (manual).

Measures the delay between a significant BTC spot move on Binance and the
corresponding Polymarket CLOB book reprice on an active BTC Up/Down market.

USAGE:
  uv run python strategies/crypto_updown/latency_probe.py --market <condition_id> --duration 3600

INTERPRETATION:
  median_reprice_lag_ms < 500   → directional repricing MAY be viable; run Tasks 4-5
  median_reprice_lag_ms >= 500  → skip Tasks 4-5, go arbitrage-only (Task 6)
  Document the measured numbers in docs/plans/04-crypto-updown-bot.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone

import websockets
import httpx

from strategies.crypto_updown.spot import parse_trade

_CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
_GAMMA_URL = "https://gamma-api.polymarket.com"
_SPOT_THRESHOLD_PCT = 0.002   # 0.2% move in 10s considered "significant"
_WINDOW_S = 10                # rolling window to detect a significant move


async def _spot_feed(symbol: str, queue: asyncio.Queue) -> None:
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@trade"
    async with websockets.connect(url) as ws:
        async for raw in ws:
            try:
                tick = parse_trade(json.loads(raw))
                await queue.put(("spot", tick.price, time.monotonic()))
            except (ValueError, KeyError):
                continue


async def _clob_feed(condition_id: str, queue: asyncio.Queue) -> None:
    async with websockets.connect(_CLOB_WS) as ws:
        await ws.send(json.dumps({"assets_ids": [condition_id], "type": "market"}))
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if isinstance(msg, list):
                    for item in msg:
                        if item.get("event_type") in ("book", "price_change"):
                            await queue.put(("clob", item, time.monotonic()))
                elif isinstance(msg, dict):
                    if msg.get("event_type") in ("book", "price_change"):
                        await queue.put(("clob", msg, time.monotonic()))
            except (ValueError, KeyError):
                continue


async def run_probe(condition_id: str, duration_s: int, symbol: str = "BTCUSDT") -> None:
    queue: asyncio.Queue = asyncio.Queue()
    spot_prices: list[tuple[float, float]] = []   # (price, mono_ts)
    clob_events: list[float] = []                 # mono_ts of each clob update
    reprice_lags_ms: list[float] = []

    print(f"Probing for {duration_s}s — spot={symbol}, market={condition_id}")
    print("Ctrl+C to stop early.\n")

    async def _collector():
        last_significant_spot_ts: float | None = None
        last_significant_price: float | None = None

        while True:
            item = await queue.get()
            kind = item[0]

            if kind == "spot":
                _, price, ts = item
                spot_prices.append((price, ts))
                # Detect significant move in rolling window
                window_start = ts - _WINDOW_S
                window = [(p, t) for p, t in spot_prices if t >= window_start]
                if len(window) >= 2:
                    oldest_p = window[0][0]
                    move_pct = abs(price - oldest_p) / oldest_p
                    if move_pct >= _SPOT_THRESHOLD_PCT:
                        last_significant_spot_ts = ts
                        last_significant_price = price

            elif kind == "clob":
                _, _msg, ts = item
                clob_events.append(ts)
                if last_significant_spot_ts is not None:
                    lag_ms = (ts - last_significant_spot_ts) * 1000
                    if 0 < lag_ms < 30_000:  # only lags < 30s are meaningful
                        reprice_lags_ms.append(lag_ms)
                        print(
                            f"  reprice lag: {lag_ms:.1f}ms  "
                            f"(spot move at {last_significant_price:.2f})"
                        )
                        last_significant_spot_ts = None  # reset until next move

    tasks = [
        asyncio.create_task(_spot_feed(symbol, queue)),
        asyncio.create_task(_clob_feed(condition_id, queue)),
        asyncio.create_task(_collector()),
    ]

    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=duration_s)
    except (asyncio.TimeoutError, KeyboardInterrupt):
        pass
    finally:
        for t in tasks:
            t.cancel()

    print(f"\n{'='*50}")
    print(f"LATENCY PROBE RESULTS — {datetime.now(tz=timezone.utc).isoformat()}")
    print(f"Symbol: {symbol}  Market: {condition_id}")
    print(f"Duration: {duration_s}s")
    print(f"Spot ticks received:   {len(spot_prices)}")
    print(f"CLOB events received:  {len(clob_events)}")
    print(f"Significant-move reprice lags measured: {len(reprice_lags_ms)}")

    if reprice_lags_ms:
        print(f"\nLag stats (ms):")
        print(f"  median: {statistics.median(reprice_lags_ms):.1f}")
        print(f"  mean:   {statistics.mean(reprice_lags_ms):.1f}")
        print(f"  min:    {min(reprice_lags_ms):.1f}")
        print(f"  max:    {max(reprice_lags_ms):.1f}")
        median_lag = statistics.median(reprice_lags_ms)
        verdict = "PROCEED with Tasks 4-5 (directional)" if median_lag < 500 else "SKIP to Task 6 (arb-only)"
        print(f"\nVERDICT: median={median_lag:.0f}ms → {verdict}")
    else:
        print("\nNo reprice lags captured — run during active BTC trading hours.")
    print("="*50)
    print("\nDocument these numbers in docs/plans/04-crypto-updown-bot.md before continuing.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", required=True, help="Polymarket condition_id for a BTC Up/Down market")
    parser.add_argument("--duration", type=int, default=3600, help="probe duration in seconds")
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance symbol")
    args = parser.parse_args()
    asyncio.run(run_probe(args.market, args.duration, args.symbol))


if __name__ == "__main__":
    main()
