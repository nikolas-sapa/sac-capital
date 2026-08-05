// Portfolio-history math for multi-day ranges.
//
// Everything here works off Alpaca's per-bar `profit_loss`, never off raw
// equity deltas. Raw equity includes deposits — the initial 100k paper funding
// showed up as a +$100,299 "June" bar on the 1Y chart. `profit_loss` is
// deposit-adjusted and sums exactly to (last equity - base_value).

export type Point = { label: string; value: number };
export type Bar = { ts: number; pnl: number };

/**
 * Sum daily P&L into buckets. Bucket value = total P&L earned in that bucket,
 * so the points always add up to the period total (bucketing raw equity
 * end-minus-start silently dropped the gap between one bucket and the next).
 */
export function bucketPnl(
  bars: Bar[],
  keyOf: (ts: number) => { key: string; label: string }
): Point[] {
  const order: string[] = [];
  const sums = new Map<string, { label: string; value: number }>();

  for (const bar of bars) {
    const { key, label } = keyOf(bar.ts);
    const existing = sums.get(key);
    if (existing) {
      existing.value += bar.pnl;
    } else {
      order.push(key);
      sums.set(key, { label, value: bar.pnl });
    }
  }

  return order.map((key) => {
    const b = sums.get(key)!;
    return { label: b.label, value: parseFloat(b.value.toFixed(2)) };
  });
}

/**
 * Alpaca's daily bars lag by a session — the last bar is yesterday's close, so
 * every multi-day range was missing today's move entirely. Fold live equity in
 * as today's P&L.
 */
export function appendLive(
  bars: Bar[],
  lastBarEquity: number | null,
  currentEquity: number | null,
  nowTs: number,
  sameDay: (a: number, b: number) => boolean
): Bar[] {
  if (lastBarEquity == null || currentEquity == null || bars.length === 0) return bars;

  const delta = currentEquity - lastBarEquity;
  const last = bars[bars.length - 1];

  // Bar already covers today (mid-session): restate it as P&L through now.
  if (sameDay(last.ts, nowTs)) {
    return [...bars.slice(0, -1), { ts: last.ts, pnl: last.pnl + delta }];
  }
  return [...bars, { ts: nowTs, pnl: delta }];
}
