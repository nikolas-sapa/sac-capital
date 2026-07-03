import type { VercelRequest, VercelResponse } from "@vercel/node";

type Handler = (req: VercelRequest, res: VercelResponse) => Promise<void> | void;

/**
 * Sanitizes upstream errors by logging details server-side and returning a generic message to the client.
 * Prevents leaking internal error details to the frontend.
 */
export function upstreamError(res: VercelResponse, status: number, detail: string): void {
  console.error(`Upstream error ${status}:`, detail);
  res.status(status).json({ error: "Failed to fetch market data" });
}

/**
 * Wraps a handler with error catching and logging.
 * Logs errors server-side and returns 502 if headers haven't been sent.
 */
export function withGuard(handler: Handler): Handler {
  return async (req, res) => {
    try {
      await handler(req, res);
    } catch (err) {
      console.error("API handler error:", err);
      if (!res.headersSent) {
        res.status(502).json({ error: "Failed to fetch market data" });
      }
    }
  };
}
