import { timingSafeEqual } from "node:crypto";

export const BOT_STATUS_BLOB_PATH = "bot-status/status.json";
export const MAX_EVENT_BODY_BYTES = 4_096;
export const MAX_WRITE_ATTEMPTS = 3;

export type RunType = "routine" | "full_scan";
export type PublishedStatus = "running" | "completed" | "failed";
export type StoredStatus = PublishedStatus | "unknown";

export type BotStatusEvent = {
  run_id: string;
  run_type: RunType;
  status: PublishedStatus;
  started_at: string;
  updated_at: string;
};

export type StoredBotStatusEvent = Omit<BotStatusEvent, "status"> & {
  status: StoredStatus;
};

export type BotStatusDocument = {
  version: 1;
  latest_activity: StoredBotStatusEvent;
  latest_full_scan: StoredBotStatusEvent;
};

export const SEED_STATUS: BotStatusDocument = {
  version: 1,
  latest_activity: {
    run_id: "20260924T110406Z",
    run_type: "routine",
    status: "completed",
    started_at: "2026-09-24T11:04:06Z",
    updated_at: "2026-09-24T11:04:06Z",
  },
  latest_full_scan: {
    run_id: "20260827T200226Z",
    run_type: "full_scan",
    status: "unknown",
    started_at: "2026-08-27T20:02:26Z",
    updated_at: "2026-08-27T20:02:26Z",
  },
};

export interface BotStatusStore {
  read(): Promise<{ document: unknown; etag: string | null }>;
  write(document: BotStatusDocument, etag: string | null): Promise<void>;
}

type BlobGetResult = {
  statusCode: number;
  stream: ReadableStream<Uint8Array> | null;
  blob: { size: number | null; etag: string };
} | null;
type BlobGetter = (
  pathname: string,
  options: { access: "private"; useCache: false },
) => Promise<BlobGetResult>;
type BlobPutter = (
  pathname: string,
  body: string,
  options: {
    access: "private";
    addRandomSuffix: false;
    allowOverwrite: boolean;
    ifMatch?: string;
    contentType: "application/json";
    cacheControlMaxAge: 60;
  },
) => Promise<unknown>;

export function createBlobStatusStore(
  blobGet: BlobGetter,
  blobPut: BlobPutter,
  isMissingError: (error: unknown) => boolean = () => false,
): BotStatusStore {
  return {
    async read() {
      try {
        const result = await blobGet(BOT_STATUS_BLOB_PATH, { access: "private", useCache: false });
        if (result === null) return { document: SEED_STATUS, etag: null };
        if (result.statusCode !== 200 || result.stream === null || result.blob.size === null) {
          throw new Error("unexpected Blob response");
        }
        if (result.blob.size > 16_384) throw new Error("status document too large");
        const text = await new Response(result.stream).text();
        return { document: JSON.parse(text) as unknown, etag: result.blob.etag };
      } catch (error) {
        if (isMissingError(error)) return { document: SEED_STATUS, etag: null };
        throw error;
      }
    },
    async write(document: BotStatusDocument, etag: string | null) {
      await blobPut(BOT_STATUS_BLOB_PATH, JSON.stringify(document), {
        access: "private",
        addRandomSuffix: false,
        allowOverwrite: etag !== null,
        ...(etag === null ? {} : { ifMatch: etag }),
        contentType: "application/json",
        cacheControlMaxAge: 60,
      });
    },
  };
}

export type StatusResponse = {
  status: number;
  body: BotStatusDocument | { error: string };
  headers?: Record<string, string>;
};

const EVENT_KEYS = [
  "run_id",
  "run_type",
  "status",
  "started_at",
  "updated_at",
] as const;
const UTC_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseTimestamp(value: unknown, nowMs: number): string {
  if (typeof value !== "string") {
    throw new Error("invalid timestamp");
  }
  const match = UTC_TIMESTAMP.exec(value);
  if (!match) throw new Error("invalid timestamp");
  const parsed = Date.parse(value);
  const date = new Date(parsed);
  const fractional = match[1] ?? "";
  const expectedMilliseconds = fractional ? Number(fractional.slice(1).padEnd(3, "0")) : 0;
  const parts = value.slice(0, 19).split(/[-T:]/).map(Number);
  if (
    !Number.isFinite(parsed) ||
    date.getUTCFullYear() !== parts[0] ||
    date.getUTCMonth() + 1 !== parts[1] ||
    date.getUTCDate() !== parts[2] ||
    date.getUTCHours() !== parts[3] ||
    date.getUTCMinutes() !== parts[4] ||
    date.getUTCSeconds() !== parts[5] ||
    date.getUTCMilliseconds() !== expectedMilliseconds ||
    parsed > nowMs
  ) {
    throw new Error("invalid timestamp");
  }
  return value;
}

function parseStoredEvent(
  value: unknown,
  nowMs: number,
  allowUnknown: boolean,
  allowExtraFields = false,
): StoredBotStatusEvent {
  if (!isRecord(value)) throw new Error("invalid event");
  if (EVENT_KEYS.some((key) => !(key in value)) || (!allowExtraFields && Object.keys(value).length !== EVENT_KEYS.length)) {
    throw new Error("invalid event fields");
  }
  if (typeof value.run_id !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(value.run_id)) {
    throw new Error("invalid run id");
  }
  if (value.run_type !== "routine" && value.run_type !== "full_scan") {
    throw new Error("invalid run type");
  }
  const allowedStatuses: StoredStatus[] = allowUnknown
    ? ["running", "completed", "failed", "unknown"]
    : ["running", "completed", "failed"];
  if (!allowedStatuses.includes(value.status as StoredStatus)) {
    throw new Error("invalid status");
  }
  const startedAt = parseTimestamp(value.started_at, nowMs);
  const updatedAt = parseTimestamp(value.updated_at, nowMs);
  if (Date.parse(updatedAt) < Date.parse(startedAt)) throw new Error("invalid timestamp order");
  return {
    run_id: value.run_id,
    run_type: value.run_type,
    status: value.status as StoredStatus,
    started_at: startedAt,
    updated_at: updatedAt,
  };
}

export function parseEventBody(body: unknown, nowMs = Date.now()): BotStatusEvent {
  let encoded: string;
  if (typeof body === "string") {
    encoded = body;
  } else if (Buffer.isBuffer(body)) {
    encoded = body.toString("utf8");
  } else {
    try {
      const serialized = JSON.stringify(body);
      if (serialized === undefined) throw new Error("invalid JSON");
      encoded = serialized;
    } catch {
      throw new Error("invalid JSON");
    }
  }
  if (Buffer.byteLength(encoded, "utf8") > MAX_EVENT_BODY_BYTES) throw new Error("body too large");
  let raw: unknown;
  try {
    raw = typeof body === "string" || Buffer.isBuffer(body) ? JSON.parse(encoded) : body;
  } catch {
    throw new Error("invalid JSON");
  }
  return parseStoredEvent(raw, nowMs, false) as BotStatusEvent;
}

export function parseStatusDocument(value: unknown, nowMs = Date.now()): BotStatusDocument {
  if (!isRecord(value) || value.version !== 1) throw new Error("invalid status document");
  const latestFullScan = parseStoredEvent(value.latest_full_scan, nowMs, true, true);
  if (latestFullScan.run_type !== "full_scan") throw new Error("invalid full scan record");
  if (
    latestFullScan.status === "unknown" &&
    (latestFullScan.run_id !== SEED_STATUS.latest_full_scan.run_id ||
      latestFullScan.started_at !== SEED_STATUS.latest_full_scan.started_at)
  ) {
    throw new Error("unknown status is restricted to the historical seed");
  }
  return {
    version: 1,
    latest_activity: parseStoredEvent(value.latest_activity, nowMs, false, true),
    latest_full_scan: latestFullScan,
  };
}

function compareRuns(a: StoredBotStatusEvent, b: StoredBotStatusEvent): number {
  const time = Date.parse(a.started_at) - Date.parse(b.started_at);
  return time || a.run_id.localeCompare(b.run_id);
}

function advance(current: StoredBotStatusEvent, event: BotStatusEvent): StoredBotStatusEvent {
  if (current.run_id === event.run_id) {
    return Date.parse(event.updated_at) >= Date.parse(current.updated_at) ? event : current;
  }
  return compareRuns(event, current) > 0 ? event : current;
}

export function mergeEvent(document: BotStatusDocument, event: BotStatusEvent): BotStatusDocument {
  return {
    version: 1,
    latest_activity: advance(document.latest_activity, event),
    latest_full_scan:
      event.run_type === "full_scan" ? advance(document.latest_full_scan, event) : document.latest_full_scan,
  };
}

export function projectPublicStatus(value: unknown, nowMs = Date.now()): BotStatusDocument {
  return parseStatusDocument(value, nowMs);
}

function tokenMatches(actual: string | undefined, expected: string): boolean {
  if (!actual?.startsWith("Bearer ") || !expected) return false;
  const supplied = Buffer.from(actual.slice(7));
  const wanted = Buffer.from(expected);
  return supplied.length === wanted.length && timingSafeEqual(supplied, wanted);
}

export async function persistEvent(
  store: BotStatusStore,
  event: BotStatusEvent,
  nowMs = Date.now(),
): Promise<BotStatusDocument> {
  let lastError: unknown;
  for (let attempt = 0; attempt < MAX_WRITE_ATTEMPTS; attempt += 1) {
    const current = await store.read();
    const document = parseStatusDocument(current.document, nowMs);
    const merged = mergeEvent(document, event);
    if (JSON.stringify(merged) === JSON.stringify(document)) return document;
    try {
      await store.write(merged, current.etag);
      return merged;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError ?? new Error("status write failed");
}

export async function handleStatusRequest(
  request: { method?: string; authorization?: string; body?: unknown },
  store: BotStatusStore,
  expectedToken: string,
  nowMs = Date.now(),
): Promise<StatusResponse> {
  try {
    if (request.method === "GET") {
      const current = await store.read();
      return {
        status: 200,
        body: projectPublicStatus(current.document, nowMs),
        headers: { "Cache-Control": "public, max-age=0, s-maxage=60, stale-while-revalidate=300" },
      };
    }
    if (request.method !== "POST") {
      return { status: 405, body: { error: "Method not allowed" }, headers: { Allow: "GET, POST" } };
    }
    if (!expectedToken) return { status: 503, body: { error: "Status unavailable" } };
    if (!tokenMatches(request.authorization, expectedToken)) {
      return { status: 401, body: { error: "Unauthorized" } };
    }
    let event: BotStatusEvent;
    try {
      event = parseEventBody(request.body, nowMs);
    } catch {
      return { status: 400, body: { error: "Invalid status event" } };
    }
    const saved = await persistEvent(store, event, nowMs);
    return { status: 200, body: projectPublicStatus(saved, nowMs) };
  } catch (error) {
    const constructorName = error instanceof Error ? error.constructor.name : undefined;
    const errorClass = typeof constructorName === "string" && /^[A-Za-z][A-Za-z0-9]*$/.test(constructorName)
      ? constructorName
      : "UnknownError";
    console.error(`Bot status storage error: ${errorClass}`);
    return { status: 503, body: { error: "Status unavailable" } };
  }
}
