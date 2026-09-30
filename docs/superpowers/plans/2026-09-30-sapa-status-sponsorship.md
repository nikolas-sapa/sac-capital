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
   - Pass: API ≥12 contract assertions; monotonicity ≥4; publisher ≥8 assertions; no public response contains extra status keys.
## Task 2: Website status and sponsorship
   - Add responsive status banner and sponsorship placements section with supplied contact email.
   - Fetch status with seeded fallback and honest unavailable state.
   - Pass: production build exits 0; screenshot check at 1440px/390px shows both sections, correct dates, relative ages, and zero console errors.
## Task 3: Repair bot launcher configuration
   - Correct broken Python executable path in launch-agent configuration using repository’s supported environment/setup path; document repair/setup steps if needed.
   - Validate both plist files and path references without loading/running agents.
   - Pass: 2/2 plists valid; each referenced executable exists or setup documentation gives the exact creation path; bot remains stopped.
## Task 4: Audit, review, and delivery
   - Run named verification checks, review whole diff, get Python/TypeScript/security/code review.
   - Preserve existing source-checkout generated-data edits.
   - Push feature branch and create PR.
   - Pass: all verifications reported with results; PR points to feature branch; no deployment or Vercel secret provisioning.
