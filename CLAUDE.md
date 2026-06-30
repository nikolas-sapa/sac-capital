# sapa_fund — Claude Instructions

## Stack
Python (backend, broker integrations, signal engine) · Next.js / TypeScript (frontend) · Alpaca (brokerage) · Supabase

## API Rules

- **Env var names:** always `grep` the project `.env` before writing any function that reads env vars. Exact names matter (`ALPACA_API_KEY_ID` not `ALPACA_KEY_ID`).
- **Alpaca portfolio history:** history endpoints lag by ~1 trading day. Always fetch live account equity (`GET /v2/account`) and append as a "Now" data point to any portfolio history chart.
- **Vercel env vars:** before `vercel env add`, run `vercel project ls` to confirm the linked project. Stale links silently write to the wrong project.

## Trading / Research Rules

- When recommending a stock entry price: anchor to BOTH fundamentals (fair value floor) AND technicals (timing gate). Never state an entry without first asking for or having ADX + oscillator data.
- For agent debates/multi-agent research: compress each agent's output to a score + 3 bullets before returning to user. Raw output is too verbose for trading decisions.
- Financial API history append pattern: `Promise.all([history, liveAccount])` → append live equity as final point.

## Current Positions
- NVDA @ $224 entry (Jun 2) — SL $205, hold for July Q2 FY2027 earnings
- Watch: TEM @ $49 limit, AVGO @ $385-390 when ADX < 45

## Architecture
- Signal engine: `sapa_fund/brain.py`
- News provider: `sapa_fund/equities/data/news.py` + `CompositeNewsProvider` pattern
- Frontend: Next.js app in `frontend/`
