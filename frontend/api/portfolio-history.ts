import type { VercelRequest, VercelResponse } from "@vercel/node";

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

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const keyId = (process.env.ALPACA_API_KEY_ID ?? process.env.ALPACA_KEY_ID ?? "").trim();
  const secret = (process.env.ALPACA_SECRET_KEY ?? "").trim();

  if (!keyId || !secret) {
    return res.status(503).json({ error: "Alpaca credentials not configured" });
  }

  const uiPeriod = String(req.query.period ?? "1W");
  const alpaca = PERIOD_MAP[uiPeriod] ?? PERIOD_MAP["1W"];
  const isIntraday = alpaca.timeframe !== "1D";

  const histUrl = `${BASE_URL}/v2/account/portfolio/history?period=${alpaca.period}&timeframe=${alpaca.timeframe}&extended_hours=false`;

  try {
    // Fetch history and current account equity in parallel
    const [histResp, acctResp] = await Promise.all([
      fetch(histUrl, { headers: HEADERS(keyId, secret) }),
      fetch(`${BASE_URL}/v2/account`, { headers: HEADERS(keyId, secret) }),
    ]);

    if (!histResp.ok) {
      const text = await histResp.text();
      return res.status(histResp.status).json({ error: text });
    }

    const raw = await histResp.json() as {
      timestamp: number[];
      equity: (number | null)[];
      profit_loss: (number | null)[];
      base_value: number;
    };

    if (!raw.timestamp?.length) {
      return res.status(200).json({ points: [] });
    }

    // Period-relative P&L: how much has the portfolio moved since period start
    const periodStartEquity = raw.equity[0] ?? raw.base_value ?? 0;

    const TZ = "Europe/Athens";
    const fmtIntraday = new Intl.DateTimeFormat("en-US", {
      timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false,
    });
    const fmtDate = new Intl.DateTimeFormat("en-US", {
      timeZone: TZ, month: "2-digit", day: "2-digit",
    });

    const points = raw.timestamp
      .map((ts, i) => {
        const equity = raw.equity[i];
        if (equity == null) return null;
        const d = new Date(ts * 1000);
        const label = isIntraday
          ? fmtIntraday.format(d)
          : fmtDate.format(d);
        return {
          label,
          value: parseFloat((equity - periodStartEquity).toFixed(2)),
        };
      })
      .filter((p): p is { label: string; value: number } => p !== null);

    // For intraday (1D) only: append a live "now" point so the chart reflects
    // current equity during market hours. Multi-day bars don't need this — Alpaca's
    // daily bars are authoritative and appending today's pre/post-market equity
    // just duplicates yesterday's value, making the chart appear stale.
    if (isIntraday && acctResp.ok) {
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
    }

    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=120");
    return res.status(200).json({ points, base_value: periodStartEquity });
  } catch (err) {
    return res.status(500).json({ error: String(err) });
  }
}
