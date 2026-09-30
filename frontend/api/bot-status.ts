import { BlobNotFoundError, get, put } from "@vercel/blob";
import type { VercelRequest, VercelResponse } from "@vercel/node";
import {
  createBlobStatusStore,
  handleStatusRequest,
  validateContentLength,
} from "./_lib/bot-status.js";

const store = createBlobStatusStore(get, put, (error) => error instanceof BlobNotFoundError);

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const rawLength = req.headers["content-length"];
  const contentLength = Array.isArray(rawLength) ? rawLength[0] : rawLength;
  if (req.method === "POST") {
    const lengthError = validateContentLength(contentLength);
    if (lengthError === "missing") {
      return res.status(411).json({ error: "Content-Length required" });
    }
    if (lengthError === "invalid") {
      return res.status(400).json({ error: "Invalid Content-Length" });
    }
    if (lengthError === "too-large") {
      return res.status(413).json({ error: "Status event too large" });
    }
  }

  const authorization = Array.isArray(req.headers.authorization)
    ? req.headers.authorization[0]
    : req.headers.authorization;
  const response = await handleStatusRequest(
    { method: req.method, authorization, body: req.body },
    store,
    (process.env.BOT_STATUS_WRITE_TOKEN ?? "").trim(),
  );
  for (const [name, value] of Object.entries(response.headers ?? {})) res.setHeader(name, value);
  return res.status(response.status).json(response.body);
}
