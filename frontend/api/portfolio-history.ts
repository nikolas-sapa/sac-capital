import type { VercelRequest, VercelResponse } from "@vercel/node";
import { upstreamError, withGuard } from "./_lib/guard.js";
import { appendLive, bucketPnl, type Bar } from "./_lib/history-math.js";

const BASE_URL =
  process.env.ALPACA_BASE_URL ?? "https://paper-api.alpaca.markets";

const PERIOD_MAP: Record<string, { period: string; timeframe: string }> = {
  "1D": { period: "1D", timeframe: "1H" },
  "1W": { period: "1W", timeframe: "1D" },
  "1M": { period: "1M", timeframe: "1D" },
  "6M": { period: "6M", timeframe: "1D" },
  "1Y": { period: "1A", timeframe: "1D" },
  "All": { period: "1A", timeframe: "1D" },
};

const HEADERS = (keyId: string, secret: string) => ({
  "APCA-API-KEY-ID": keyId,
  "APCA-API-SECRET-KEY": secret,
  Accept: "application/json",
});

async function handler(req: VercelRequest, res: VercelResponse) {
  const keyId = (process.env.ALPACA_API_KEY_ID ?? process.env.ALPACA_KEY_ID ?? "").trim();
  const secret = (process.env.ALPACA_SECRET_KEY ?? "").trim();

  if (!keyId || !secret) {
    return res.status(503).json({ error: "Alpaca credentials not configured" });
  }

  const uiPeriod = String(req.query.period ?? "1W");

  // Validate period against allowed values
  if (!(uiPeriod in PERIOD_MAP)) {
    const allowedPeriods = Object.keys(PERIOD_MAP).join(", ");
    return res.status(400).json({ error: `Invalid period. Allowed: ${allowedPeriods}` });
  }

  const alpaca = PERIOD_MAP[uiPeriod];
  const isIntraday = alpaca.timeframe !== "1D";

  const histUrl = `${BASE_URL}/v2/account/portfolio/history?period=${alpaca.period}&timeframe=${alpaca.timeframe}&extended_hours=false`;

  // Fetch history and current account equity in parallel
  const [histResp, acctResp] = await Promise.all([
    fetch(histUrl, { headers: HEADERS(keyId, secret) }),
    fetch(`${BASE_URL}/v2/account`, { headers: HEADERS(keyId, secret) }),
  ]);

  if (!histResp.ok) {
    const text = await histResp.text();
    return upstreamError(res, histResp.status, text);
  }

  const raw = await histResp.json() as {
    timestamp: number[];
    equity: (number | null)[];
    profit_loss: (number | null)[];
    base_value: number;
  };

  if (!Array.isArray(raw.timestamp) || !raw.timestamp.length) {
    return res.status(200).json({ points: [] });
  }

  if (!Array.isArray(raw.equity) || !Array.isArray(raw.profit_loss)) {
    return res.status(200).json({ points: [] });
  }

  // Baseline is always `base_value` — the equity just before the window opened.
  // Intraday: the first 1H bar is already mid-session, so baselining on it
  // subtracted out the day's gain and flipped Today's P&L negative.
  // Multi-day: `profit_loss` sums to (last equity - base_value), so this keeps
  // the % denominator consistent with the P&L the chart shows.
  const periodStartEquity = raw.base_value ?? raw.equity[0] ?? 0;

  const TZ = "Europe/Athens";
  const fmtIntraday = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false,
  });
  const fmtDate = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ, month: "2-digit", day: "2-digit",
  });

  let points: { label: string; value: number }[];
  let totalPnl: number;

  if (isIntraday) {
    // 1D: cumulative P&L from session open, with a live "now" point
    points = raw.timestamp
      .map((ts, i) => {
        const equity = raw.equity[i];
        if (equity == null) return null;
        return {
          label: fmtIntraday.format(new Date(ts * 1000)),
          value: parseFloat((equity - periodStartEquity).toFixed(2)),
        };
      })
      .filter((p): p is { label: string; value: number } => p !== null);

    if (acctResp.ok) {
      const acct = await acctResp.json() as { equity?: string };
      const currentEquity = acct.equity ? parseFloat(acct.equity) : null;
      if (currentEquity != null) {
        const nowPnl = parseFloat((currentEquity - periodStartEquity).toFixed(2));
        const nowLabel = fmtIntraday.format(new Date());
        const last = points[points.length - 1];
        if (last && last.label === nowLabel) {
          points[points.length - 1] = { label: nowLabel, value: nowPnl };
        } else {
          points.push({ label: "Now", value: nowPnl });
        }
      }
    } else {
      console.warn(`Failed to fetch live equity for intraday chart: ${acctResp.status} ${acctResp.statusText}`);
    }
    totalPnl = points.length > 0 ? points[points.length - 1].value : 0;

  } else {
    // Multi-day: every bucket is a SUM of Alpaca's per-bar `profit_loss`.
    // 1W → one bar per day, 1M → weekly buckets, longer → monthly buckets.
    // Bucketing raw equity instead (a) dropped the gain between one bucket's
    // last bar and the next one's first, and (b) counted the initial 100k paper
    // funding as a +$100,299 "June" profit bar on the 1Y chart.
    let bars: Bar[] = raw.timestamp
      .map((ts, i) => (raw.profit_loss[i] == null ? null : { ts, pnl: raw.profit_loss[i]! }))
      .filter((b): b is Bar => b !== null);

    // Daily bars lag a session — fold today's live equity in as today's P&L.
    if (acctResp.ok) {
      const acct = await acctResp.json() as { equity?: string };
      const lastEquity = [...raw.equity].reverse().find((e) => e != null) ?? null;
      bars = appendLive(
        bars,
        lastEquity,
        acct.equity ? parseFloat(acct.equity) : null,
        Math.floor(Date.now() / 1000),
        (a, b) => fmtDate.format(new Date(a * 1000)) === fmtDate.format(new Date(b * 1000))
      );
    } else {
      console.warn(`Failed to fetch live equity for chart: ${acctResp.status} ${acctResp.statusText}`);
    }

    const fmtMonth = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "short" });
    const fmtYearMonth = new Intl.DateTimeFormat("en-US", { timeZone: TZ, year: "numeric", month: "short" });
    const fmtYearWeek = new Intl.DateTimeFormat("en-US", {
      timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
    });

    // Continuous week index, so a week spanning a month boundary stays one bucket.
    const weekKey = (d: Date) => {
      const parts = fmtYearWeek.formatToParts(d);
      const get = (t: string) => parts.find((p) => p.type === t)!.value;
      const local = new Date(`${get("year")}-${get("month")}-${get("day")}T00:00:00Z`);
      return String(Math.floor((local.getTime() / 86400000 + 4) / 7));
    };

    let weekIndex = 0;
    const seenWeeks = new Set<string>();
    const keyOf = (ts: number) => {
      const d = new Date(ts * 1000);
      if (uiPeriod === "1W") return { key: fmtDate.format(d), label: fmtDate.format(d) };
      if (uiPeriod === "1M") {
        const key = weekKey(d);
        if (!seenWeeks.has(key)) { seenWeeks.add(key); weekIndex += 1; }
        return { key, label: `Week ${weekIndex}` };
      }
      return { key: fmtYearMonth.format(d), label: fmtMonth.format(d) };
    };

    points = bucketPnl(bars, keyOf);
    totalPnl = points.reduce((s, p) => s + p.value, 0);
  }

  res.setHeader("Cache-Control", "private, no-store");
  return res.status(200).json({ points, totalPnl: parseFloat(totalPnl.toFixed(2)), base_value: periodStartEquity });
}

export default withGuard(handler);
