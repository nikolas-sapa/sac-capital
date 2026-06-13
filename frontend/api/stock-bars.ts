import type { VercelRequest, VercelResponse } from "@vercel/node";

const DATA_URL = "https://data.alpaca.markets";

type AlpacaBar = {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

function dateRange(period: string): { start: string; end: string } {
  // end = yesterday: Alpaca daily bars for today aren't finalized until market close
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  const days: Record<string, number> = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365,
  };
  start.setDate(start.getDate() - (days[period] ?? 30));
  const fmt = (d: Date) => d.toISOString().split("T")[0];
  return { start: fmt(start), end: fmt(end) };
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const ticker = (req.query.ticker as string | undefined)?.toUpperCase().trim();
  const period = (req.query.period as string | undefined) ?? "1M";

  if (!ticker) return res.status(400).json({ error: "ticker required" });

  const keyId = (process.env.ALPACA_API_KEY_ID ?? process.env.ALPACA_KEY_ID ?? "").trim();
  const secret = (process.env.ALPACA_SECRET_KEY ?? "").trim();

  if (!keyId || !secret) return res.status(503).json({ error: "Alpaca credentials not configured" });

  const { start, end } = dateRange(period);
  const url = `${DATA_URL}/v2/stocks/${encodeURIComponent(ticker)}/bars?timeframe=1Day&start=${start}&end=${end}&adjustment=raw`;

  try {
    const r = await fetch(url, {
      headers: {
        "APCA-API-KEY-ID": keyId,
        "APCA-API-SECRET-KEY": secret,
        Accept: "application/json",
      },
    });

    if (!r.ok) {
      const text = await r.text();
      return res.status(r.status).json({ error: text });
    }

    const data = await r.json();
    const bars: AlpacaBar[] = data.bars ?? [];

    const points = bars.map((b) => ({
      t: b.t, o: b.o, h: b.h, l: b.l, c: b.c,
    }));

    res.setHeader("Cache-Control", "s-maxage=900, stale-while-revalidate=1800");
    return res.status(200).json({ ticker, points });
  } catch (err) {
    return res.status(500).json({ error: String(err) });
  }
}
