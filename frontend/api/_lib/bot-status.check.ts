// Run: node api/_lib/bot-status.check.ts
import assert from "node:assert/strict";
import {
  MAX_EVENT_BODY_BYTES,
  SEED_STATUS,
  createBlobStatusStore,
  handleStatusRequest,
  mergeEvent,
  persistEvent,
  projectPublicStatus,
  validateContentLength,
  type BotStatusDocument,
  type BotStatusEvent,
  type BotStatusStore,
} from "./bot-status.ts";

const NOW = Date.parse("2026-09-30T12:00:00Z");
const TOKEN = "test-writer-token";
const AUTH = `Bearer ${TOKEN}`;
assert.equal(validateContentLength(undefined), "missing");
assert.equal(validateContentLength("not-a-length"), "invalid");
assert.equal(validateContentLength(String(MAX_EVENT_BODY_BYTES)), null);
assert.equal(validateContentLength(String(MAX_EVENT_BODY_BYTES + 1)), "too-large");
const event: BotStatusEvent = {
  run_id: "20260930T100000Z",
  run_type: "routine",
  status: "running",
  started_at: "2026-09-30T10:00:00Z",
  updated_at: "2026-09-30T10:00:00Z",
};

class MemoryStore implements BotStatusStore {
  document: unknown;
  etag: string | null = "v1";
  writes = 0;
  failWrites = 0;

  constructor(document: unknown = structuredClone(SEED_STATUS)) {
    this.document = document;
  }

  async read() {
    return { document: structuredClone(this.document), etag: this.etag };
  }

  async write(document: BotStatusDocument) {
    this.writes += 1;
    if (this.failWrites > 0) {
      this.failWrites -= 1;
      this.etag = `v${this.writes + 1}`;
      throw new Error("conditional write failed: private detail");
    }
    this.document = structuredClone(document);
    this.etag = `v${this.writes + 1}`;
  }
}

// API contract: method, auth, schema, bounds, timestamps, persistence, projection, errors.
const projected = projectPublicStatus({
  ...SEED_STATUS,
  secret: "must-not-leak",
  latest_activity: { ...SEED_STATUS.latest_activity, balance: 1000 },
}, NOW);
assert.deepEqual(Object.keys(projected).sort(), ["latest_activity", "latest_full_scan", "version"]);
assert.deepEqual(Object.keys(projected.latest_activity).sort(), [
  "run_id", "run_type", "started_at", "status", "updated_at",
]);
assert.equal("secret" in projected, false);
assert.equal("balance" in projected.latest_activity, false);
assert.throws(() => projectPublicStatus({ ...SEED_STATUS, latest_activity: { ...SEED_STATUS.latest_activity, status: "unknown" } }, NOW));
assert.throws(() => projectPublicStatus({ ...SEED_STATUS, latest_full_scan: { ...SEED_STATUS.latest_full_scan, run_id: "another-run" } }, NOW));

const getResponse = await handleStatusRequest({ method: "GET" }, new MemoryStore(), TOKEN, NOW);
assert.equal(getResponse.status, 200);
assert.deepEqual(getResponse.body, SEED_STATUS);

assert.equal((await handleStatusRequest({ method: "POST", body: event }, new MemoryStore(), TOKEN, NOW)).status, 401);
assert.equal((await handleStatusRequest({ method: "POST", authorization: "Bearer wrong", body: event }, new MemoryStore(), TOKEN, NOW)).status, 401);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: event }, new MemoryStore(), "", NOW)).status, 503);
assert.equal((await handleStatusRequest({ method: "PUT" }, new MemoryStore(), TOKEN, NOW)).status, 405);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: "{" }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: { ...event, extra: true } }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: { ...event, status: "unknown" } }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: { ...event, run_type: "weekly" } }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: { ...event, started_at: "today" } }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: { ...event, started_at: "2026-02-30T10:00:00Z" } }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: { ...event, updated_at: "2026-10-01T00:00:00Z" } }, new MemoryStore(), TOKEN, NOW)).status, 400);
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: `${JSON.stringify(event)}${" ".repeat(MAX_EVENT_BODY_BYTES)}` }, new MemoryStore(), TOKEN, NOW)).status, 400);

const routineStore = new MemoryStore();
const routinePost = await handleStatusRequest({ method: "POST", authorization: AUTH, body: event }, routineStore, TOKEN, NOW);
assert.equal(routinePost.status, 200);
assert.equal(routineStore.writes, 1);
assert.equal((routinePost.body as BotStatusDocument).latest_activity.status, "running");

const fullScan = { ...event, run_id: "20260930T110000Z", run_type: "full_scan" as const, status: "completed" as const, started_at: "2026-09-30T11:00:00Z", updated_at: "2026-09-30T11:30:00Z" };
const fullResponse = await handleStatusRequest({ method: "POST", authorization: AUTH, body: fullScan }, routineStore, TOKEN, NOW);
assert.equal(fullResponse.status, 200);
assert.equal((fullResponse.body as BotStatusDocument).latest_full_scan.run_id, fullScan.run_id);

const originalError = console.error;
const logged: unknown[][] = [];
console.error = (...args: unknown[]) => { logged.push(args); };
const logSentinel = "SENTINEL_PRIVATE_DETAIL";
const storageError = await handleStatusRequest(
  { method: "GET" },
  { read: async () => { throw new Error(logSentinel); }, write: async () => undefined },
  TOKEN,
  NOW,
);
console.error = originalError;
assert.deepEqual(storageError, { status: 503, body: { error: "Status unavailable" } });
assert.equal(JSON.stringify(storageError).includes("private"), false);
assert.equal(JSON.stringify(logged).includes(logSentinel), false);
assert.match(String(logged[0]?.[0]), /^Bot status storage error: [A-Za-z][A-Za-z0-9]*$/);

// A fresh private store reads the seed and creates the fixed object without an ETag.
let firstWrite: { pathname: string; options: Record<string, unknown> } | undefined;
const missingBlobStore = createBlobStatusStore(
  async () => null,
  async (pathname, _body, options) => { firstWrite = { pathname, options }; },
);
assert.deepEqual(await missingBlobStore.read(), { document: SEED_STATUS, etag: null });
await missingBlobStore.write(SEED_STATUS, null);
assert.equal(firstWrite?.pathname, "bot-status/status.json");
assert.equal(firstWrite?.options.allowOverwrite, false);
assert.equal("ifMatch" in (firstWrite?.options ?? {}), false);

// Monotonicity: old runs lose, newer runs win, same run updates, full scans update both slots.
const older = { ...event, run_id: "20260901T000000Z", started_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" };
assert.equal(mergeEvent(SEED_STATUS, older).latest_activity.run_id, SEED_STATUS.latest_activity.run_id);
const newer = mergeEvent(SEED_STATUS, event);
assert.equal(newer.latest_activity.run_id, event.run_id);
const completed = { ...event, status: "completed" as const, updated_at: "2026-09-30T10:05:00Z" };
assert.equal(mergeEvent(newer, completed).latest_activity.status, "completed");
const changedIdentity = { ...completed, run_type: "full_scan" as const, started_at: "2026-09-30T09:00:00Z" };
assert.equal((await handleStatusRequest({ method: "POST", authorization: AUTH, body: changedIdentity }, new MemoryStore(newer), TOKEN, NOW)).status, 400);
const afterScan = mergeEvent(newer, fullScan);
assert.equal(afterScan.latest_activity.run_id, fullScan.run_id);
assert.equal(afterScan.latest_full_scan.run_id, fullScan.run_id);
assert.equal(mergeEvent(afterScan, older).latest_activity.run_id, fullScan.run_id);

const retryStore = new MemoryStore();
retryStore.failWrites = 2;
assert.equal((await persistEvent(retryStore, event, NOW)).latest_activity.run_id, event.run_id);
assert.equal(retryStore.writes, 3);

console.log("bot-status: contract and monotonicity checks passed");
