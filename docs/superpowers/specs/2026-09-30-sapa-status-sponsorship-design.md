# Sapa bot freshness and sponsorship

## Interpretation

Publish public run freshness (latest bot activity and latest full scan) and a sponsorship/ad placement inquiry on the existing SAC Capital site. Repair the local bot launcher configuration identified by the audit. Preserve pre-existing generated-data edits in the original checkout.

## Context

- Public app: Vite + React + TypeScript on Vercel (`frontend/`).
- Bot: Python equity runner; current launch-agent points at a missing `.venv`, and the scanner launch-agent is not loaded.
- Contact: `nikolas@helpmarq.com`.
- Latest historical any-run event: 2026-09-24 14:04 EEST (mark/exits); latest full scan attempt: 2026-08-27 23:02 EEST. The older scan record has no outcome field, so display outcome as unknown.
- Status feed uses a fixed private Vercel Blob JSON object containing timestamps and run metadata only. Writer uses an authenticated server API; public reader emits a strict allow-list. Conditional ETag writes prevent older/concurrent events overwriting newer state.

## Desired behavior

1. The global navigation shows a compact bot-activity chip with the latest run age. Activating it opens a centered accessible dialog, separate from the hero section, with latest activity and latest full-scan relative ages and exact Europe/Athens date/times.
2. Initial status is seeded from verified historical run records; full scan outcome remains explicitly unknown.
3. Subsequent runner starts/completions update durable status. Status publishing errors log a warning and never change the bot's trading/run result.
4. Sponsorship and on-site ad placements are described as accepting inquiries, with a mailto link to the supplied address.
5. Status responses and stored status contain no portfolio, credentials, order, or financial data.
6. Missing/unavailable status storage degrades to seeded status plus an honest availability note; page remains usable.
7. Repair launch-agent Python path to use the project environment managed by the documented setup. Do not launch the bot during repair.

## Architecture and data contract

- `GET /api/bot-status`: reads private Blob server-side, then returns public allow-listed latest activity and latest full scan fields.
- Event shape: `{ run_id, run_type: "routine" | "full_scan", status: "running" | "completed" | "failed", started_at, updated_at }`; ISO 8601 UTC timestamps. `unknown` is allowed only for the seeded historical scan outcome.
- Stored shape: `{ version: 1, latest_activity, latest_full_scan }`. Each slot advances by started time (then run id for ties); an event for the same run updates its status. Use bounded conditional ETag retry to prevent lost writes.
- `POST /api/bot-status`: accepts only an authenticated bot status event; validates bounded JSON and timestamps; persists to a private Blob with conditional ETag writes.
- Runtime config: `BLOB_READ_WRITE_TOKEN` and `BOT_STATUS_WRITE_TOKEN`, required in Preview and Production and for the bot publisher.
- Seed JSON in `frontend/public/` provides the historical fallback and supports local preview.
- Runner emits `running` and terminal `completed`/`failed` events using existing HTTP client dependency and a short timeout.
- UI computes “time ago” from timestamps; no static relative-time claims after deployment.

## Acceptance criteria

- Status handler passes 100% of positive/negative contract checks, including auth, schema, timestamp, method, persistence, and response filtering cases.
- Runner tests prove 100% of valid start/success/failure paths emit valid metadata and 100% of publisher failures leave the runner result unchanged.
- Frontend build exits 0; both new sections render at desktop (1440px) and mobile (390px), with no browser console errors.
- The displayed history matches the two dates above; full scan outcome reads unknown.
- Existing bot and portfolio code behavior remains unchanged except status reporting and launcher path correction.

## Non-goals

- Restarting or executing the bot.
- Deploying to production, creating/configuring a Blob store, or provisioning secrets in Vercel.
- Building an ad-serving system, payment flow, sponsor CRM, or inquiry form.
- Rewriting analytics, portfolio data, historical runs, or trading logic.
- Committing or overwriting the pre-existing generated-data edits in the user's original checkout.
