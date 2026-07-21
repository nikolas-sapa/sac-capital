<p align="center"><img src="https://raw.githubusercontent.com/nikolas-sapa/sac-capital/main/frontend/public/sac-capital.png" width="320" /></p>

# SAC Capital

> AI trading decisions are exported as deterministic `bytes32` commitments and anchored on Mantle — anyone can verify agent behavior and outcomes.

**Track:** AI Alpha & Data · Turing Test Hackathon 2026

| | |
|---|---|
| Demo | [sapa-fund.vercel.app](https://sapa-fund.vercel.app) |
| Contract | [`0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887`](https://explorer.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887) |
| Deploy tx | [`0x46bbaa...`](https://explorer.mantle.xyz/tx/0x46bbaa02a9e7fd1025f00896c70405978cc3596e04d0559e07c5c1b0cac1222b) |

## Install the CLI

```sh
uv tool install sac-capital   # or: pip install sac-capital
sac setup                     # step-by-step wizard — connect LLM, broker, alerts
sac doctor                    # verify config
sac run                       # equities pipeline (paper trading)
```

Runs on your Claude subscription via the `claude` CLI (no API key
required) — Anthropic/OpenAI API keys and Codex optional. Every wizard
step is skippable; config lives in `~/.sac-capital/`. Full guide:
[INSTALL.md](https://github.com/nikolas-sapa/sac-capital/blob/main/INSTALL.md).

| Command | Does |
|---|---|
| `sac setup` | interactive setup wizard (subscription-first, paper-only) |
| `sac run` | full equities screen → analyst → risk kernel → paper orders |
| `sac research` | supplier-lag research runner (`--static-only` etc.) |
| `sac doctor` | preflight checks; `--llm` adds a live LLM probe |
| `sac verify` | export deterministic decision commitment hashes |

---

## How It Works

```
US Equity Event Screen
  → Haiku pre-filter
  → Sonnet bull thesis
  → Sonnet challenger
  → Auditor
  → News Guard (FOMC/CPI/NFP blackout — new entries only)
  → Risk Kernel (quarter-Kelly, per-name/sector caps, correlation gate, drawdown breaker)
  → Live-trading guard (refuses any non-paper order)
  → Alpaca paper order + local ledger entry
  → Deterministic canonical JSON exporter
  → AgentDecisionRegistry on Mantle (bytes32 SHA-256 commitment)
  → Frontend verification panel
```

Mantle is the immutable benchmark layer. The agent hashes each decision payload with canonical JSON → SHA-256 → `bytes32`, records it on-chain, and can later anchor outcome hashes against the same decision ID. The frontend recomputes the hash client-side so reviewers can confirm the on-chain record matches the AI output.

**Safety boundary:** paper-only. On-chain records are verifiability anchors — not custody, brokerage, or live-trading instructions.

---

## Risk Table

These are the live fuses. **Values here must match `.env`** — if you loosen a limit, change it here in the same commit and say why. A previous "aggressive profile" block in `.env` silently overrode every one of these while this README advertised the conservative numbers; that divergence is the failure mode this table exists to prevent.

| Fuse | Default | Env key | Enforced at |
|---|---|---|---|
| Kelly fraction | 0.25 (quarter) | `KELLY_FRACTION` | `equities/risk/sizing.py` (hard-capped at 0.5 regardless) |
| Max per-name | 25% | `EQUITY_MAX_NAME_PCT` | `equities/risk/kernel.py` |
| Max per-sector | 35% | `EQUITY_MAX_SECTOR_PCT` | `equities/risk/kernel.py` |
| Daily realized-loss halt | 5% | `EQUITY_DAILY_LOSS_LIMIT_PCT` | `equities/risk/kernel.py` |
| Drawdown circuit-breaker | 15% from HWM | `EQUITY_DRAWDOWN_LIMIT_PCT` | `equities/risk/kernel.py` + `state.py` |
| Max pairwise correlation | 0.70 | `EQUITY_MAX_PAIRWISE_CORR` | `equities/risk/correlation.py` |
| Max portfolio avg correlation | 0.50 | `EQUITY_MAX_PORTFOLIO_CORR` | `equities/risk/correlation.py` |
| Macro blackout window | 24h before / 2h after | `EQUITY_NEWS_BLACKOUT_BEFORE_H` / `_AFTER_H` | `equities/risk/news_guard.py` |

**Correlation gate.** Sector-string matching is not a concentration check: the swing universe is semiconductor-heavy, so five "different" names can be one bet. The gate correlates actual daily returns over a 90d lookback. It **fails open** on missing price data — a provider outage silently disables it, which is the deliberate trade against halting all entries on a yfinance hiccup.

**Macro blackout.** Blocks *new entries* near high-impact US FOMC/CPI/NFP releases. Exits, stops and trailing logic are never blocked — getting out is always allowed. Primary source is the free ForexFactory feed; `equities/risk/macro_events_fallback.csv` is the offline fallback and **fails closed** outside its declared coverage window. The 24h/2h window suits daily bars (the classic 30min/15min window is an intraday setting). Re-verify the fallback dates annually against federalreserve.gov and bls.gov — BLS shifts CPI/NFP around holidays.

**Overfitting gate.** `equities/eval/overfitting.py` implements PBO (via CSCV), Deflated and Probabilistic Sharpe. `AutoPromoter` cannot promote a variant unless the verdict passes (PBO < 0.5 **and** DSR > 0.95) against the *full* set of tournament trials, not just the winner. Fails closed on insufficient data. Note: `run_tournament`/`AutoPromoter` currently have no production caller — this gate is preventive, in place before the self-improvement loop is wired up. Whoever wires a real `score_fn` must verify trial columns actually disperse; if they collapse, DSR's multiple-comparison correction becomes a silent no-op.

## Live-Trading Lock

Live trading is **off by design and refuses rather than routes**. A non-paper order requires all three of:

1. non-paper config (`ALPACA_PAPER=false` + a non-paper base URL),
2. `ALLOW_LIVE_TRADING=1` in the environment,
3. `live_trading_enabled=True` in settings.

Enforced at `equities/execution/alpaca.py::_assert_live_trading_allowed`, called as the first line of `_submit_order` — the single choke point both `buy()` and `sell()` route through. Deliberately redundant with the constructor check; do not "simplify" either away. **Any new broker executor must call this guard too** — it is not inherited automatically.

Verify with `uv run python scripts/check_live_trading_guard.py`.

The equities research side now also includes a paper-only supplier-lag research runner:

```sh
uv run runner-research --static-only
uv run runner-research --strategy-backtest --static-only
```

`runner-research` saves the top research candidates to `data/research_candidates.json` and appends historical strategy backtests to `data/strategy_backtests.jsonl` when trades exist.

---

## Reproduce Locally

**Dependencies**

```sh
uv sync
```

**Tests**

```sh
./.venv/bin/python -m pytest
```

**Export decision commitments**

```sh
./.venv/bin/python scripts/export_mantle_commitments.py \
  --ledger data/ledger.db \
  --out data/mantle_commitments.jsonl
```

**Dry-run Mantle submission**

```sh
./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract 0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887 \
  --agent-id mantle-verifiable-ai-agent \
  --limit 1
```

**Deploy contract** (Foundry required, funded Mantle wallet)

```sh
export MANTLE_RPC_URL=https://rpc.mantle.xyz
export MANTLE_PRIVATE_KEY=0x...

forge test
forge script contracts/script/DeployAgentDecisionRegistry.s.sol \
  --rpc-url "$MANTLE_RPC_URL" \
  --broadcast
```

**Frontend**

```sh
cd frontend
npm install
npm run dev
```

---

## Repository Layout

```
cli/              `sac` CLI — banner, setup wizard, workdir, dispatcher
core/             Config, ledgers, alerts, LLM adapters (incl. claude_cli subscription provider)
equities/
  analysis/       Equity analyst, typed LLM schemas, budget controls
  data/           Prices, fundamentals, calendar, filings, news, macro, VIX
  eval/           Research artifact replay and report
  execution/      Alpaca paper execution and reconciliation
  killgate/       Forward-paper tracker and promotion gates
  research/       Artifact store and offline research modules
  risk/           Sizing, exits, risk kernel
  screen/         Event, quality, inflection, thematic, relative-strength, politician
contracts/        AgentDecisionRegistry.sol (Mantle)
scripts/          Commitment exporter, Mantle submission, nightly maintenance
runner_research.py Paper-only supplier-lag research runner
frontend/         React/Vite verification dashboard
tests/            790-test regression suite
docs/             Operator runbooks
deploy/           macOS launchd plists
```

---

## Equities Pipeline

`runner_equities.py` runs the full loop:

1. Mark open positions and check exits
2. Classify macro regime
3. Check thesis health on open swing positions
4. Check thematic concentration
5. Run event screen (earnings + recent 8-K catalysts)
6. Add relative-strength, trend, base, breakout-volume evidence
7. Run quality and inflection screens
8. Apply VIX entry gate
9. Run LLM pre-filter → analyst → challenger → auditor
10. Validate with Pydantic; reject malformed outputs
11. Write research artifacts for all analysed candidates
12. Pass through risk kernel
13. Submit Alpaca paper orders or internal paper fills

**Optional — Politician disclosure screen** (off by default). When
`POLITICIAN_SIGNAL_ENABLED=true`, a stage after relative-strength pulls recent
US congressional STOCK Act buy disclosures (public House + Senate filings),
scores them deterministically (recency, cluster, repeat-buyer, size), and feeds
scored candidates into the same analyst funnel. Public-disclosure lag research
only — not insider data, not copy-trading. Source feed URL is config-injected so
the canonical House Clerk / Senate eFD sources can be swapped in without code
changes.

---

## Key Configuration

```sh
EXECUTION_PROVIDER=internal_paper   # never alpaca_live
LIVE_TRADING_ENABLED=false
EQUITY_RISK_PCT=0.005
EQUITY_MAX_POSITIONS=12
EQUITY_MAX_SECTOR_PCT=0.35
EQUITY_DAILY_LOSS_LIMIT_PCT=0.05

# Alpaca paper
ALPACA_PAPER=true
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_API_KEY_ID=...
ALPACA_SECRET_KEY=...

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_ALERT_MODE=critical   # critical | verbose

# LLM
ANTHROPIC_FAST_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_STRONG_MODEL=claude-sonnet-4-6

# Politician disclosure screen (off by default)
POLITICIAN_SIGNAL_ENABLED=false
# Feed URLs default to public House/Senate stock-watcher mirrors; override to
# point at canonical sources. POLITICIAN_HOUSE_URL / POLITICIAN_SENATE_URL
```

---

## Team

| Name | Role |
|---|---|
| **Nikolas Sapalidis** | Lead Developer — architecture, Mantle integration, AI pipeline, frontend, investment strategy |
| **Konstantopoulos Ilias** | Safety features & stock research |
| **George Apostolakis** | Investment strategy & Mantle network funding |

[nikolas.helpmarq.com](https://nikolas.helpmarq.com)
