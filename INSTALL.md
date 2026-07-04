# Install SAC Capital

Requirements: Python ≥ 3.12. For subscription mode: the `claude` CLI
(`npm i -g @anthropic-ai/claude-code`), logged in to your Claude account.

## Option A — uv tool (recommended)

    uv tool install git+https://github.com/nikolas-sapa/sac-capital
    # or, from PyPI once published:
    uv tool install sac-capital

## Option B — pip

    pip install sac-capital

## Option C — clone (development)

    git clone https://github.com/nikolas-sapa/sac-capital && cd sac-capital
    uv sync

## Set up

    sac setup

The wizard detects the `claude` CLI and defaults to **subscription mode**
(no API key, billed to your Claude plan). Alternatives offered: Anthropic
API key, OpenAI key, or Codex CLI. Every other step (Alpaca paper keys,
Tiingo, Telegram, Mantle anchoring) is optional — press Enter to skip.

Config and data live in `~/.sac-capital/` (override with `SAC_HOME`).
Running inside a cloned repo with a `.env` uses the repo directory instead.

## Verify

    sac doctor          # config + connectivity checks
    sac doctor --llm    # adds one live LLM probe call

If web crawling features complain about a missing browser:

    playwright install chromium

## Run

    sac run                      # equities pipeline (paper trading)
    sac research --static-only   # research runner
    sac verify                   # export decision commitment hashes

SAC Capital is **paper-only by default**. Live trading requires manually
editing `.env` and setting an explicit confirmation env var — the wizard
never enables it.

## Set up inside Claude Code

Open the repo (or any folder) in Claude Code and paste:

> Install sac-capital with `uv tool install sac-capital`, then run
> `sac setup` and walk me through each prompt, then `sac doctor`.
