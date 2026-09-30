# Implementation plan: Sapa bot freshness and sponsorship

## Global constraints

- Follow `docs/superpowers/specs/2026-09-30-sapa-status-sponsorship-design.md` and the test plan.
- Public status metadata only; strict schema; writer secret from environment only.
- Keep status reporting best-effort so telemetry errors cannot interrupt bot processing.
- Use Vercel Blob SDK already selected by project architecture. Add dependency only if absent, and verify official current docs before coding.
- Use existing design tokens: Geist Sans, `#006bff`, no orange or emoji.
- Keep work in branch `codex/sapa-status-sponsorship`; do not touch original checkout’s generated-data modifications.
- No bot execution, deploy, or secret provisioning.

## Non-goals

- Ad-serving, billing, lead database, trading changes, historical-data rewrites, bot execution, production deploy, Vercel secret/store setup.

## Tasks

## Task 1: Bot status service and publisher
- Add validated `GET`/authenticated `POST /api/bot-status`, fixed private Blob key, timestamp ordering with conditional ETag writes, public response projection, bounded request body, and sanitized errors.
- Add historical seed from known successful 2026-09-24 activity and unknown-outcome 2026-08-27 full scan.
- Add best-effort start/completion/failure publisher to the runner and focused tests.
- Document the two runtime secrets and the Preview/Production setup gate.
- Files: `frontend/api/bot-status.ts`, `frontend/api/_lib/bot-status.ts`, `frontend/api/_lib/bot-status.check.ts`, `frontend/public/bot-status-seed.json`, `frontend/package.json`, `frontend/package-lock.json`, `runner_equities.py`, `core/config.py`, `tests/test_bot_status.py`, `deploy/README.md`, `.env.example` (if one exists).
- Pass: API ≥12 contract assertions; monotonicity ≥4; publisher ≥8 assertions; no public response contains extra status keys.

## Task 2: Website status and sponsorship
- Add responsive status banner and sponsorship placements section with supplied contact email.
- Fetch status with seeded fallback and honest unavailable state.
- Files: `frontend/src/App.tsx`, `frontend/src/components/sections/BotStatusBanner.tsx`, `frontend/src/components/sections/SponsorSection.tsx`, `frontend/index.html` only if Geist needs adding.
- Pass: production build exits 0; screenshot check at 1440px/390px shows both sections, correct dates, relative ages, and zero console errors.

## Task 3: Repair bot launcher configuration
- Replace the missing `.venv/bin/python` executable with `/opt/homebrew/bin/uv run --project /Users/nikolassapalidis/Developer/python/sapa_fund python` in the mark and scan agent arguments. Keep `WorkingDirectory` at the project root so `.env` and relative paths continue to resolve.
- Document environment auto-creation and secret setup; validate both plist files and `uv` executable path without loading/running agents.
- Files: `deploy/com.polymarketbot.equities.mark.plist`, `deploy/com.polymarketbot.equities.scan.plist`, `deploy/README.md`.
- Pass: 2/2 plists valid; `/opt/homebrew/bin/uv` executable; each command references the Python entry point and supported project root; bot remains stopped.

## Task 4: Audit, review, and delivery
- Run named verification checks, review whole diff, get Python/TypeScript/security/code review.
- Preserve existing source-checkout generated-data edits.
- Push feature branch and create PR.
- Pass: all verifications reported with results; PR points to feature branch; no deployment or Vercel secret provisioning.
