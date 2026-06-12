import type { VercelRequest, VercelResponse } from "@vercel/node";

const BASE_URL =
  process.env.ALPACA_BASE_URL ?? "https://paper-api.alpaca.markets";

// Map our UI period to Alpaca params
const PERIOD_MAP: Record<string, { period: string; timeframe: string }> = {
  "1D": { period: "1D", timeframe: "15Min" },
  "1W": { period: "1W", timeframe: "1D" },
  "1M": { period: "1M", timeframe: "1D" },
  "6M": { period: "6M", timeframe: "1D" },
  "1Y": { period: "1A", timeframe: "1D" },
  "All": { period: "1A", timeframe: "1D" },
};

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const keyId = (process.env.ALPACA_API_KEY_ID ?? process.env.ALPACA_KEY_ID ?? "").trim();
  const secret = (process.env.ALPACA_SECRET_KEY ?? "").trim();

  if (!keyId || !secret) {
    return res.status(503).json({ error: "Alpaca credentials not configured" });
  }

  const uiPeriod = String(req.query.period ?? "1W");
  const alpaca = PERIOD_MAP[uiPeriod] ?? PERIOD_MAP["1W"];

  const url = `${BASE_URL}/v2/account/portfolio/history?period=${alpaca.period}&timeframe=${alpaca.timeframe}&extended_hours=false`;

  try {
    const response = await fetch(url, {
      headers: {
        "APCA-API-KEY-ID": keyId,
        "APCA-API-SECRET-KEY": secret,
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      const text = await response.text();
      return res.status(response.status).json({ error: text });
    }

    const raw = await response.json() as {
      timestamp: number[];
      equity: number[];
      profit_loss: number[];
      base_value: number;
    };

    if (!raw.timestamp?.length) {
      return res.status(200).json({ points: [] });
    }

    const base = raw.base_value ?? raw.equity[0] ?? 0;
    const points = raw.timestamp.map((ts, i) => {
      const d = new Date(ts * 1000);
      const isIntraday = alpaca.timeframe !== "1D";
      const label = isIntraday
        ? `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
        : `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
      return {
        label,
        value: parseFloat(((raw.equity[i] ?? base) - base).toFixed(2)),
      };
    });

    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=120");
    return res.status(200).json({ points, base_value: base });
  } catch (err) {
    return res.status(500).json({ error: String(err) });
  }
}
