import { BlobNotFoundError, get, put } from "@vercel/blob";
import type { VercelRequest, VercelResponse } from "@vercel/node";
import {
  createBlobStatusStore,
  handleStatusRequest,
} from "./_lib/bot-status.js";

const store = createBlobStatusStore(get, put, (error) => error instanceof BlobNotFoundError);

export default async function handler(req: VercelRequest, res: VercelResponse) {
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
