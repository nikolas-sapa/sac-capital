import type { VercelRequest, VercelResponse } from "@vercel/node";
import { upstreamError, withGuard } from "./_lib/guard";

const BASE_URL =
  process.env.ALPACA_BASE_URL ?? "https://paper-api.alpaca.markets";

async function handler(req: VercelRequest, res: VercelResponse) {
  const keyId = (process.env.ALPACA_API_KEY_ID ?? process.env.ALPACA_KEY_ID ?? "").trim();
  const secret = (process.env.ALPACA_SECRET_KEY ?? "").trim();

  if (!keyId || !secret) {
    return res.status(503).json({ error: "Alpaca credentials not configured" });
  }

  try {
    const response = await fetch(`${BASE_URL}/v2/positions`, {
      headers: {
        "APCA-API-KEY-ID": keyId,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
      },
    });

    if (!response.ok) {
      const text = await response.text();
      return upstreamError(res, response.status, text);
    }

    const raw = await response.json();

    if (!Array.isArray(raw)) {
      return res.status(200).json([]);
    }

    const positions = raw.map((p: AlpacaPosition, i) => ({
      id: p.asset_id ?? String(i),
      ticker: p.symbol,
      side: p.side,
      status: "open" as const,
      shares: p.qty != null ? parseFloat(p.qty) : null,
      entry_price: p.avg_entry_price != null ? parseFloat(p.avg_entry_price) : null,
      mark_price: p.current_price != null ? parseFloat(p.current_price) : null,
      stop_loss: null,
      take_profit: null,
      unrealized_pnl: p.unrealized_pl != null ? parseFloat(p.unrealized_pl) : null,
      realized_pnl: null,
      exit_price: null,
      exit_reason: null,
      confidence: null,
      strategy: "alpaca_live",
      mode: "paper",
      opened_at: null,
      closed_at: null,
    }));

    res.setHeader("Cache-Control", "private, no-store");
    return res.status(200).json(positions);
}

export default withGuard(handler);

type AlpacaPosition = {
  asset_id?: string;
  symbol: string;
  side: string;
  qty?: string;
  avg_entry_price?: string;
  current_price?: string;
  unrealized_pl?: string;
};
