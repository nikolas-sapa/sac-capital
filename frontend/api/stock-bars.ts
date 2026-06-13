import type { VercelRequest, VercelResponse } from "@vercel/node";

const DATA_URL = "https://data.alpaca.markets";

type AlpacaBar = {
  t: string; // timestamp ISO
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const ticker = (req.query.ticker as string | undefined)?.toUpperCase().trim();
  const period = (req.query.period as string | undefined) ?? "1M";

  if (!ticker) return res.status(400).json({ error: "ticker required" });

  const keyId = (process.env.ALPACA_API_KEY_ID ?? process.env.ALPACA_KEY_ID ?? "").trim();
  const secret = (process.env.ALPACA_SECRET_KEY ?? "").trim();

  if (!keyId || !secret) return res.status(503).json({ error: "Alpaca credentials not configured" });

  const limitMap: Record<string, number> = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 252,
  };
  const limit = limitMap[period] ?? 30;

  try {
    const url = `${DATA_URL}/v2/stocks/${encodeURIComponent(ticker)}/bars?timeframe=1Day&limit=${limit}&feed=iex&adjustment=raw`;
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
      t: b.t,
      o: b.o,
      h: b.h,
      l: b.l,
      c: b.c,
      v: b.v,
    }));

    res.setHeader("Cache-Control", "s-maxage=900, stale-while-revalidate=1800");
    return res.status(200).json({ ticker, points });
  } catch (err) {
    return res.status(500).json({ error: String(err) });
  }
}
