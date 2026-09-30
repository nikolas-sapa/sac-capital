# Test plan: Sapa bot freshness and sponsorship

## Global constraints

- No secrets, portfolio values, orders, or credentials in public status storage/API.
- Historical full-scan outcome must remain `unknown`.
- Status reporting must not fail the bot run.
- Do not start the bot or deploy/provision infrastructure.
- Preserve generated-data edits in the original checkout.

## Test plan (before implementation)

1. **API contract checks** (`npm run check:bot-status`): at least 16 assertions pass: accepts each allowed run kind/event; rejects missing/wrong token, unknown fields, invalid enum, malformed/oversized JSON, missing/invalid/over-4096-byte `Content-Length`, future/invalid timestamps, unsupported method; GET filters private/unrecognized fields; storage error returns sanitized error.
2. **Status monotonicity checks**: at least 4 assertions pass for old/new timestamps, duplicate event, full-scan updates, and preventing an older activity from replacing newer state.
3. **Runner publisher checks** (`tests/test_bot_status.py`): at least 8 assertions pass for started/completed/failed payload shape, full vs routine run kind, auth header, endpoint absence behavior, timeout, HTTP error, and network exception isolation.
4. **Frontend build** (`npm run build`): exits 0 after type-checking both website source and `api/**/*.ts` with no TypeScript errors.
5. **Frontend/browser check**: at 1440px and 390px widths, status chip appears in the global navigation with no status strip before the hero; activation opens a centered dialog separate from the hero; Escape and close restore focus; both dates and relative ages show; sponsor email is correct; horizontal overflow count is 0.
6. **Static audit check**: API response/status fixture excludes all extra keys and matches seeded dates; count 0 portfolio/pricing/credential fields.
7. **Launcher configuration check**: 2 plist files parse successfully and each configured executable path resolves to the project environment path; do not load agents or execute Python bot.

## Failure policy

Fix each failed criterion and rerun that named check. Do not claim verification for any check not executed.
