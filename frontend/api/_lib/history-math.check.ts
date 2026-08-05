// Run: node api/_lib/history-math.check.ts
// ponytail: one assert-based check, no test framework.
import assert from "node:assert/strict";
import { appendLive, bucketPnl, type Bar } from "./history-math.ts";

const DAY = 86400;
const bars: Bar[] = [
  { ts: 0 * DAY, pnl: 100 },
  { ts: 1 * DAY, pnl: -40 },
  { ts: 7 * DAY, pnl: 25 },
];
const sameDay = (a: number, b: number) => Math.floor(a / DAY) === Math.floor(b / DAY);

// Buckets sum to the period total — the equity-delta version lost the gap
// between one bucket's last bar and the next bucket's first.
const weekly = bucketPnl(bars, (ts) => {
  const w = Math.floor(ts / (7 * DAY));
  return { key: String(w), label: `Week ${w + 1}` };
});
assert.deepEqual(weekly, [
  { label: "Week 1", value: 60 },
  { label: "Week 2", value: 25 },
]);
assert.equal(weekly.reduce((s, p) => s + p.value, 0), 85);

// A deposit must not show up as profit: profit_loss is deposit-adjusted, so a
// 100k funding day contributes 0.
const funded = bucketPnl([{ ts: 0, pnl: 0 }, { ts: DAY, pnl: 12 }], () => ({ key: "m", label: "Jun" }));
assert.deepEqual(funded, [{ label: "Jun", value: 12 }]);

// Live equity becomes today's bar when the history lags a session...
const lagged = appendLive(bars, 1000, 1150, 8 * DAY, sameDay);
assert.deepEqual(lagged[lagged.length - 1], { ts: 8 * DAY, pnl: 150 });
assert.equal(lagged.length, bars.length + 1);

// ...and restates the existing bar when it already covers today.
const sameDayBars = appendLive(bars, 1000, 1150, 7 * DAY, sameDay);
assert.equal(sameDayBars.length, bars.length);
assert.deepEqual(sameDayBars[2], { ts: 7 * DAY, pnl: 175 });

// Missing live equity is a no-op, never a zeroed chart.
assert.deepEqual(appendLive(bars, 1000, null, 8 * DAY, sameDay), bars);

console.log("history-math: ok");
