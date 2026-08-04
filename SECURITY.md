# Security Policy

## Reporting a Vulnerability

Report vulnerabilities privately to **niksapa150@gmail.com**, or via
[GitHub Security Advisories](https://github.com/nikolas-sapa/sac-capital/security/advisories/new).
Do **not** open a public issue for a security report.

Include what you found, steps to reproduce, and the potential impact. We aim
to acknowledge reports within 5 business days and will work with you on
coordinated disclosure before any public writeup.

## Supported Versions

This project is in active pre-1.0 development. Only the latest commit on
`main` is supported; there are no maintained release branches.

## Scope and Known Limitations

- **The Solidity contracts are unaudited.** `contracts/AgentDecisionRegistry.sol`
  has not gone through an external security audit. It stores hash commitments
  only — it never custodies funds — but treat it as unaudited code. Do not
  deploy it, or route real value through it, expecting audit-grade guarantees.
- **Do not connect a funded wallet.** Any Mantle deployer key used with this
  repo should hold only the minimum gas needed for testnet or hackathon use.
  Never use a wallet holding unrelated funds as `MANTLE_PRIVATE_KEY`.
- **Do not enable live trading.** The agent is paper-trading only by default
  (`EXECUTION_PROVIDER=internal_paper`, `LIVE_TRADING_ENABLED=false`,
  `ALPACA_PAPER=true`). This software has not been reviewed for safe use with
  a live brokerage account, and running it against real capital is at your
  own risk.
- **`.env` holds live credentials.** LLM API keys, Alpaca keys, Telegram
  tokens, and `MANTLE_PRIVATE_KEY` all live in `.env`. It is gitignored —
  keep it that way, never commit it, and never paste its contents into an
  issue, PR, or chat log.

## Reporting Non-Security Bugs

Non-security bugs go through the normal
[issue tracker](https://github.com/nikolas-sapa/sac-capital/issues) using the
bug report template.
