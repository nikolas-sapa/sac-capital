import { BlobNotFoundError, get, put } from "@vercel/blob";
import type { VercelRequest, VercelResponse } from "@vercel/node";
import {
  BOT_STATUS_BLOB_PATH,
  SEED_STATUS,
  handleStatusRequest,
  type BotStatusDocument,
  type BotStatusStore,
} from "./_lib/bot-status.js";

const store: BotStatusStore = {
  async read() {
    try {
      const result = await get(BOT_STATUS_BLOB_PATH, { access: "private", useCache: false });
      if (result.statusCode !== 200) throw new Error("unexpected Blob response");
      if (result.blob.size > 16_384) throw new Error("status document too large");
      const text = await new Response(result.stream).text();
      return { document: JSON.parse(text) as unknown, etag: result.blob.etag };
    } catch (error) {
      if (error instanceof BlobNotFoundError) return { document: SEED_STATUS, etag: null };
      throw error;
    }
  },
  async write(document: BotStatusDocument, etag: string | null) {
    await put(BOT_STATUS_BLOB_PATH, JSON.stringify(document), {
      access: "private",
      addRandomSuffix: false,
      allowOverwrite: etag !== null,
      ...(etag === null ? {} : { ifMatch: etag }),
      contentType: "application/json",
      cacheControlMaxAge: 60,
    });
  },
};

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
