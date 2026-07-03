# SAC Capital CLI — Design

Date: 2026-07-04
Status: approved (approach A — thin wrapper CLI)

## Goal

Make the repo a distributable CLI anyone can install, set up step by step
(in Claude Code or any terminal), and run on their **Claude subscription**
via the `claude` CLI — with API keys (Anthropic/OpenAI) and Codex as
opt-in alternatives.

## Decisions

- Name: **SAC Capital**. Command: `sac`. Package: `sac-capital` (unchanged in pyproject).
- Approach: thin wrapper — new `cli/` module, stdlib `argparse`, reuse existing runners. No new dependencies.
- Distribution: GitHub (`uv tool install git+...`, clone + `uv sync`) **and** PyPI (`pip install sac-capital`).
- Setup: interactive `sac setup` wizard + `INSTALL.md` docs. No Claude Code skill.
- Logo: ASCII banner only (no image work).
- Paper-only stays the hard default; wizard never touches `LIVE_TRADING_ENABLED`.

## 1. CLI surface

Entry point in `pyproject.toml`: `sac = "cli.main:main"`.

| Command | Wraps |
|---|---|
| `sac` | ASCII banner + help |
| `sac setup` | new wizard (`cli/setup.py`) |
| `sac run` | `runner_equities:main` |
| `sac research` | `runner_research:main` (flags pass through) |
| `sac doctor` | `scripts/preflight.py` |
| `sac verify` | decision hash/commitment verification (existing exporter logic) |

Existing entry points (`runner`, `runner-equities`, `runner-research`) stay.

## 2. Provider logic — subscription-first

- Add explicit `LLM_PROVIDER=claude_cli` value to `core/claude_client.py`
  so the `claude` CLI (subscription billing) is a first-class provider,
  not just a Codex fallback.
- Wizard detection order: `claude` CLI on PATH & logged in → default
  `claude_cli`; otherwise offer `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  or `codex` — user picks.
- Existing `LLMClient` chain otherwise unchanged.

## 3. Wizard (`sac setup`)

Steps, each skippable, sensible defaults:

1. **LLM auth** — detect subscription (`claude` CLI) → else API key/codex.
2. **Alpaca paper keys** — skip = internal paper ledger (`EXECUTION_PROVIDER=internal_paper`).
3. **Tiingo key** — skip = yfinance only.
4. **Telegram** — optional bot token + chat id.
5. **Mantle anchoring** — optional, off by default.
6. **Risk params** — accept defaults ($1000 bankroll, 0.5 Kelly, 2% cap) or edit.

Output: writes `.env` (refuses to overwrite without confirmation),
then runs `sac doctor`. Never writes `LIVE_TRADING_ENABLED=true`.

## 4. Distribution

- PyPI wheel/sdist excludes `frontend/`, `contracts/`, `hackathon/`,
  `docs/`, `spike/`, `tests/` (hatchling include/exclude config).
- Heavy deps (playwright, crawl4ai, scikit-learn) stay in core deps for
  now; extras split is a later slimming pass.
- `INSTALL.md`: uv tool install, pip install, clone + uv sync, and a
  "set up inside Claude Code" walkthrough (open repo, run `sac setup`).
- Note: "SAC Capital" collides with the well-known hedge fund name;
  accepted by owner.

## 5. Logo

`cli/banner.py` — ASCII "SAC CAPITAL" wordmark, printed on bare `sac`
and at wizard start, followed by one-line paper-only disclaimer.
Monochrome (no color deps).

## 6. Testing

One `tests/test_cli.py`:
- wizard writes expected `.env` in temp dir (scripted answers via stdin monkeypatch)
- provider detection order (claude CLI present/absent)
- subcommand dispatch maps to correct targets
- `claude_cli` provider accepted by `LLMClient`

## Out of scope

- Live trading enablement, extras/dep slimming, image logo, Claude Code
  skill, frontend changes, contract changes.
