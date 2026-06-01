"""
Task 2 — LATENCY GATE (manual).

Measures the delay between a significant BTC spot move on Binance and the
corresponding Polymarket CLOB book reprice on an active BTC Up/Down market.

USAGE (three ways to supply the market):

  # Auto-discover live BTC Up/Down markets (requires VPN routing terminal traffic):
  uv run python strategies/crypto_updown/latency_probe.py --discover

  # Extract condition_id from a Polymarket market URL you copied from the browser:
  uv run python strategies/crypto_updown/latency_probe.py --url "https://polymarket.com/event/btc-..."

  # Pass the condition_id directly (fastest):
  uv run python strategies/crypto_updown/latency_probe.py --market 0xabc...123 --duration 3600

HOW TO GET THE CONDITION ID WITHOUT VPN IN THE TERMINAL:
  1. Open polymarket.com in your VPN browser
  2. Find any "Will BTC be higher/lower at ..." market
  3. Open browser DevTools → Network tab → reload → find a request to gamma-api.polymarket.com
  4. Copy the conditionId value from the JSON response
  OR: the URL slug can be resolved via --url flag below.

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
_CLOB_REST = "https://clob.polymarket.com"
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


def _resolve_token_ids(condition_id: str) -> list[str]:
    """Resolve YES/NO token IDs from a condition ID via the CLOB REST API."""
    try:
        resp = httpx.get(f"{_CLOB_REST}/markets/{condition_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        tokens = data.get("tokens", [])
        return [t["token_id"] for t in tokens if t.get("token_id")]
    except Exception as e:
        print(f"[!] Could not resolve token IDs: {e} — falling back to condition_id")
        return [condition_id]


async def _clob_feed(condition_id: str, queue: asyncio.Queue, token_ids: list[str] | None = None) -> None:
    if token_ids is None:
        token_ids = await asyncio.get_event_loop().run_in_executor(None, _resolve_token_ids, condition_id)
    print(f"  Subscribing to {len(token_ids)} token(s)")
    async with websockets.connect(_CLOB_WS) as ws:
        await ws.send(json.dumps({"assets_ids": token_ids, "type": "market"}))
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


async def run_probe(condition_id: str, duration_s: int, symbol: str = "BTCUSDT", token_ids: list[str] | None = None) -> None:
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
        asyncio.create_task(_clob_feed(condition_id, queue, token_ids=token_ids)),
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


def _discover_markets() -> list[tuple[str, str]]:
    """Try to fetch live BTC Up/Down markets from the Gamma API."""
    try:
        resp = httpx.get(
            f"{_GAMMA_URL}/markets?active=true&closed=false&limit=200",
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        markets = resp.json()
        if not isinstance(markets, list):
            markets = markets.get("markets", [])
        found = []
        for m in markets:
            q = m.get("question", "").lower()
            cid = m.get("conditionId", "")
            if cid and any(w in q for w in ["btc", "bitcoin"]) and any(
                w in q for w in ["higher", "lower", "up", "down"]
            ):
                found.append((cid, m.get("question", "")))
        return found
    except Exception as e:
        print(f"[!] Could not reach Gamma API: {e}")
        return []


def _cid_from_url(url: str) -> str | None:
    """Extract conditionId from a Polymarket event URL slug via the API."""
    import re
    slug_match = re.search(r"polymarket\.com/event/([^/?#]+)", url)
    if not slug_match:
        print("[!] Could not parse slug from URL:", url)
        return None
    slug = slug_match.group(1)
    print(f"Resolving slug: {slug}")
    try:
        resp = httpx.get(
            f"{_GAMMA_URL}/events?slug={slug}",
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else [data]
        for event in events:
            markets = event.get("markets", [])
            for m in markets:
                q = m.get("question", "").lower()
                if any(w in q for w in ["btc", "bitcoin", "higher", "lower"]):
                    cid = m.get("conditionId", "")
                    if cid:
                        return cid
            # fallback: first market in the event
            if markets and markets[0].get("conditionId"):
                return markets[0]["conditionId"]
    except Exception as e:
        print(f"[!] Could not resolve URL: {e}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket/Binance latency probe")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--market", help="Polymarket condition_id for a BTC Up/Down market")
    group.add_argument("--discover", action="store_true", help="Auto-discover live BTC Up/Down markets via Gamma API")
    group.add_argument("--url", help="Polymarket event URL (e.g. https://polymarket.com/event/btc-...)")
    parser.add_argument("--tokens", help="Comma-separated token IDs (skips CLOB REST lookup)")
    parser.add_argument("--duration", type=int, default=3600, help="probe duration in seconds")
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance symbol")
    args = parser.parse_args()

    condition_id = args.market

    if args.discover:
        print("Discovering live BTC Up/Down markets...")
        markets = _discover_markets()
        if not markets:
            print("[!] No markets found. Make sure your VPN is routing terminal traffic.")
            print("    Alternatively use: --url <polymarket_url>  or  --market <condition_id>")
            return
        print(f"\nFound {len(markets)} BTC Up/Down market(s):")
        for i, (cid, q) in enumerate(markets[:5]):
            print(f"  [{i}] {cid[:20]}... | {q[:70]}")
        condition_id = markets[0][0]
        print(f"\nUsing: {condition_id}")

    elif args.url:
        condition_id = _cid_from_url(args.url)
        if not condition_id:
            print("[!] Could not extract condition_id from URL. Try --market directly.")
            return

    if not condition_id:
        parser.error("Provide one of: --market <id>, --discover, or --url <polymarket_url>")

    token_ids = [t.strip() for t in args.tokens.split(",")] if args.tokens else None
    asyncio.run(run_probe(condition_id, args.duration, args.symbol, token_ids=token_ids))


if __name__ == "__main__":
    main()
