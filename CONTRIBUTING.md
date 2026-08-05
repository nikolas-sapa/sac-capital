# Contributing to SAC Capital

## Repo layout

```
cli/        `sac` CLI — banner, setup wizard, workdir, dispatcher
core/       Config, ledgers, alerts, LLM adapters
equities/   Analysis, data, screens, risk kernel, execution, research
contracts/  AgentDecisionRegistry.sol (Mantle)
frontend/   React/Vite verification dashboard
scripts/    Commitment exporter, Mantle submission, maintenance
tests/      Regression suite (pytest)
docs/       Operator runbooks
```

## Python setup

Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/nikolas-sapa/sac-capital
cd sac-capital
uv sync
```

Run the test suite:

```sh
playwright install chromium   # once — the Senate eFD tests launch a real browser
./.venv/bin/python -m pytest
```

Without the browser binary, four `test_senate_efd_disclosures` tests fail with
`BrowserType.launch: Executable doesn't exist`. That is a missing dependency,
not a broken build.

Run the agent locally (paper trading only — this is the default and the
only supported mode for contributors):

```sh
uv run sac setup   # interactive wizard: LLM provider, Alpaca paper keys, alerts
uv run sac doctor  # verify config before running
uv run sac run     # full equities pipeline against Alpaca paper
```

`EXECUTION_PROVIDER=internal_paper` and `LIVE_TRADING_ENABLED=false` are the
defaults in `.env.example`. Do not submit changes that flip these defaults.

## Working on the contracts

`contracts/AgentDecisionRegistry.sol` is a Foundry project. Install
[Foundry](https://book.getfoundry.sh/getting-started/installation), then:

```sh
forge test
```

Contract changes need accompanying tests in `contracts/test/`. Do not deploy
or broadcast transactions as part of a PR — deployment is a maintainer-only,
manual step against a dedicated wallet (see `contracts/README.md`).

## Working on the frontend

```sh
cd frontend
npm install
npm run dev
```

The frontend is a read-only verification dashboard: it recomputes decision
hashes client-side and compares them against the on-chain record. It does not
place trades or hold keys.

## Pull requests

- Keep PRs focused on one change.
- Add or update tests for any change to `equities/risk/`, `equities/execution/`,
  or `contracts/`.
- Run `pytest` (and `forge test` for contract changes) before opening the PR.
- Do not commit secrets, API keys, or `.env` — check `.env.example` for the
  variable name instead of inventing a new one.
- Describe what changed and why; link any related issue.

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities instead of
opening a public issue.
