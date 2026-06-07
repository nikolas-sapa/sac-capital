# Mantle-Verifiable AI Prediction Agent

One-line pitch: AI prediction-market decisions are exported as deterministic `bytes32` commitments and anchored on Mantle so judges can verify agent behavior and outcomes.

Hackathon track: `AI Alpha & Data`

Submission placeholders:

- Public demo: `TODO`
- Demo video: `TODO`
- Mantle contract address: `TODO`
- Mantle Explorer verification link: `TODO`

Architecture:

```text
Bot / LLM strategies
  -> paper ledger + research artifacts
  -> deterministic commitment exporter
  -> AgentDecisionRegistry on Mantle
  -> frontend verification and reputation demo
```

Mantle is the immutable benchmark layer: the bot keeps rich off-chain payloads public, hashes them with canonical JSON, records decision hashes on Mantle, and can later record outcome hashes against the original decision IDs. The frontend shows both the payload and the recomputed hash so reviewers can verify that the on-chain record matches the AI decision.

Safety boundary: this remains paper-only. On-chain records are verifiability anchors for decisions and outcomes; they are not custody, brokerage, or live-trading instructions.

## Hackathon Repro Steps

Install Python dependencies:

```sh
uv sync
```

Run tests:

```sh
./.venv/bin/python -m pytest
```

Export decision commitments:

```sh
./.venv/bin/python scripts/export_mantle_commitments.py \
  --ledger data/ledger.db \
  --out data/mantle_commitments.jsonl
```

Run a dry-run Mantle submission:

```sh
./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract 0x0000000000000000000000000000000000000001 \
  --agent-id mantle-verifiable-polymarket-agent \
  --limit 1
```

Deploy the contract after installing Foundry and funding a dedicated Mantle deployer wallet:

```sh
export MANTLE_RPC_URL=https://rpc.sepolia.mantle.xyz
export MANTLE_PRIVATE_KEY=0x...

forge test
forge script contracts/script/DeployAgentDecisionRegistry.s.sol \
  --rpc-url "$MANTLE_RPC_URL" \
  --broadcast
```

Submit one decision only after setting the real registry address:

```sh
export AGENT_REGISTRY_ADDRESS=0x...
export AGENT_ID=mantle-verifiable-polymarket-agent

./.venv/bin/python scripts/submit_mantle_decisions.py \
  --commitments data/mantle_commitments.jsonl \
  --contract "$AGENT_REGISTRY_ADDRESS" \
  --agent-id "$AGENT_ID" \
  --limit 1 \
  --send
```

Run the frontend locally:

```sh
cd frontend
npm install
npm run dev
```

For live Mantle event reads, set these before building or deploying the frontend:

```sh
VITE_MANTLE_RPC_URL=https://rpc.sepolia.mantle.xyz
VITE_AGENT_REGISTRY_ADDRESS=0x...
VITE_MANTLE_EXPLORER_BASE=https://sepolia.mantlescan.xyz
```

Vercel deployment: use `frontend/` as the project root, build command `npm run build`, and output directory `dist`.

# Polymarket Bot

Paper-trading research system for prediction markets and US equities.

The repo is built to test research ideas, log evidence, replay outcomes, and keep execution behind paper-only fuses. It does not contain a live-trading implementation path.

Suggested GitHub description:

```text
Paper-trading research system for Polymarket and US equities with LLM analysis, risk fuses, auditable artifacts, Alpaca paper execution, and replay evaluation.
```

Suggested GitHub topics:

```text
polymarket, prediction-markets, equities, paper-trading, algorithmic-trading, llm, risk-management, alpaca, backtesting, python
```

## What It Does

- Scans Polymarket markets and US equities for paper-trading opportunities.
- Uses deterministic screens before any LLM call.
- Runs LLM analysis with typed validation and rejection paths.
- Stores research artifacts so every analysed equity candidate can be audited.
- Applies portfolio risk fuses before paper orders.
- Supports internal paper fills and Alpaca paper brokerage orders.
- Reconciles Alpaca paper order state back into the local ledger.
- Replays stored equity research artifacts against historical prices.
- Runs locally via CLI or macOS `launchd`.

## Safety Boundary

This project is paper-only.

- `LIVE_TRADING_ENABLED` must remain false.
- `EXECUTION_PROVIDER=internal_paper` is the default.
- `EXECUTION_PROVIDER=alpaca_paper` is restricted to Alpaca paper URLs.
- Alpaca live URLs are rejected by the executor.
- Submitted broker orders are not treated as filled positions.
- Forward-paper entries are only recorded after actual broker fills or internal paper fills.

## Main Entry Points

```text
runner.py             Polymarket paper runner
runner_equities.py    US equities paper runner
runner_research.py    Offline research runner
scripts/run_nightly.py Nightly maintenance wrapper
```

## Repository Layout

```text
core/                 Shared config, ledgers, CLOB clients, alerts, LLM adapters
strategies/           Polymarket, weather, crypto, and LLM probability strategies
orchestrator/         Strategy allocation, performance, reconciliation, risk
harness/              Approval, calibration, retuning, nightly self-improvement
equities/
  analysis/           Equity analyst, prompts, typed LLM schemas, budget controls
  data/               Prices, fundamentals, calendar, filings, news, macro, VIX
  eval/               Research artifact replay and report command
  execution/          Alpaca paper execution and reconciliation
  killgate/           Forward-paper tracker and promotion gates
  research/           Artifact store and offline research modules
  risk/               Sizing, exits, risk kernel
  screen/             Event, quality, inflection, thematic, relative-strength screens
docs/                 Plans and operator runbooks
deploy/               macOS launchd plists
tests/                Regression suite
```

## Equities Pipeline

`runner_equities.py` runs the equity loop:

1. Mark open positions and check exits.
2. Classify macro regime.
3. Check thesis health on open swing positions.
4. Check thematic concentration.
5. Run event screen for earnings and recent 8-K catalysts.
6. Add relative-strength, trend, base, breakout-volume, and do-not-chase evidence.
7. Run core quality screen.
8. Run inflection screen.
9. Stop here when `--no-analyse` is used.
10. Apply VIX entry gate.
11. Run LLM prefilter, analyst, challenger, and auditor.
12. Validate LLM output with Pydantic.
13. Write research artifacts for accepted and rejected analysed candidates.
14. Pass recommendations through risk kernel.
15. Open internal paper positions or submit Alpaca paper orders.
16. Print a run summary with stages, runtime, failures, and budget.

## Equity Risk Controls

The runner passes live ledger state into `RiskKernel.approve()`:

- current equity
- same-day realized PnL
- open positions
- sector lookup
- configured max positions
- configured daily-loss halt
- configured drawdown halt
- configured sector cap
- configured name cap
- configured per-trade risk

Bad market data rejects before an analyst prompt is built:

- missing price
- zero price
- NaN or non-finite price
- stale latest bar

Invalid LLM output rejects before a `Recommendation` exists:

- malformed JSON
- missing required buy fields
- `entry <= 0`
- `stop_loss >= entry`
- `take_profit <= entry`
- confidence outside `[0, 1]`
- empty catalyst or thesis
- missing structured memo fields
- missing evidence citations

## Alpaca Paper Discipline

Alpaca execution is paper-only and guarded:

- rejects non-paper Alpaca settings
- rejects non-paper Alpaca base URLs
- checks account buying power before buy orders
- enforces local max notional
- uses deterministic `client_order_id`
- skips duplicate active client order IDs on rerun
- submits buy orders as day limit orders at the recommendation entry
- records broker orders as `submitted`, `partially_filled`, `open`, `canceled`, `expired`, or `rejected`
- reconciles `filled_avg_price` and filled quantity from broker state
- does not record a forward-paper trade for unfilled submitted orders

## Research Artifacts

Analysed equity candidates are appended to:

```text
data/research_artifacts.jsonl
```

Artifacts include:

- as-of timestamp
- ticker
- candidate evidence
- source hashes
- LLM model
- prompt hash
- raw output
- parsed output
- confidence
- accepted/rejected/error decision
- rejection reason

Replay reports use these artifacts to evaluate strategy changes before they affect paper order flow.

## Commands

Install dependencies:

```sh
uv sync
```

Run all tests:

```sh
./.venv/bin/python -m pytest
```

Run equity-focused tests:

```sh
./.venv/bin/python -m pytest tests/equities tests/test_equity_ledger.py tests/test_runner_equities_reconcile_cli.py tests/test_prices.py tests/test_fundamentals_enriched.py tests/test_macro_regime.py
```

Screen equities without LLM analysis:

```sh
./.venv/bin/python runner_equities.py --no-analyse
```

Mark positions and exits only:

```sh
./.venv/bin/python runner_equities.py --mark-only
```

Run broker reconciliation only:

```sh
./.venv/bin/python runner_equities.py --reconcile-only
```

Run a no-write equity pass:

```sh
./.venv/bin/python runner_equities.py --dry-run
```

Replay research artifacts:

```sh
./.venv/bin/python -m equities.eval.report --validation-start 2026-01-01
```

## Configuration

Settings are loaded from `.env` through `core/config.py`.

Important equity settings:

```text
EXECUTION_PROVIDER=internal_paper
LIVE_TRADING_ENABLED=false
EQUITY_LEDGER_PATH=data/equity.db
EQUITY_RISK_PCT=0.02
EQUITY_MAX_POSITIONS=4
EQUITY_MAX_NAME_PCT=0.25
EQUITY_MAX_SECTOR_PCT=0.35
EQUITY_DAILY_LOSS_LIMIT_PCT=0.05
EQUITY_DRAWDOWN_LIMIT_PCT=0.15
EQUITY_MAX_PRICE_AGE_DAYS=7
EQUITY_PROVIDER_TIMEOUT_SECONDS=10
EQUITY_PROVIDER_RETRIES=1
EQUITY_RUNNER_MAX_RUNTIME_SECONDS=600
EQUITY_RUNNER_MAX_PROVIDER_FAILURES=20
EQUITY_RUNNER_MAX_LLM_FAILURES=5
EQUITY_RUNNER_DRY_RUN=false
MAX_ORDER_USD=25
MAX_DAILY_ORDER_COUNT=3
```

Alpaca paper settings:

```text
EXECUTION_PROVIDER=alpaca_paper
ALPACA_PAPER=true
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_API_KEY_ID=...
ALPACA_SECRET_KEY=...
```

## LLM Routing

The project can route LLM calls through:

- local Codex CLI / ChatGPT login first
- Anthropic SDK as the programmatic fallback when the primary path is exhausted or fails
- OpenAI API when explicitly selected with `LLM_PROVIDER=openai`
- Anthropic SDK when explicitly selected with `LLM_PROVIDER=anthropic`
- Claude CLI when explicitly selected with `LLM_PROVIDER=claude`

If `ANTHROPIC_API_KEY` is set, the default Codex path can fall back to the
Anthropic API when the primary provider hits a quota-style failure.

Anthropic uses its own fast/strong model knobs:

- `ANTHROPIC_FAST_MODEL=claude-haiku-4-5-20251001`
- `ANTHROPIC_STRONG_MODEL=claude-sonnet-4-6`

Model mapping:

- fast tasks use Haiku 4.5
- reasoning / stronger tasks use Sonnet 4.6

The equity analyst still treats LLM output as untrusted. Parsed outputs must pass typed schema checks before becoming recommendations.

## Operations

macOS `launchd` plists live in `deploy/`.

Useful logs:

```sh
tail -f data/equities_mark.log
tail -f data/equities_scan.log
tail -f data/alpaca_reconcile.log
tail -f data/nightly.log
```

See [docs/equities-hardening.md](docs/equities-hardening.md) for the operator hardening runbook.

## Before Any Live Trading Design

Live trading is out of scope. Before a separate live design is even considered:

- paper Alpaca reconciliation must be clean over a meaningful sample
- replay reports must show enough validation trades
- expectancy must be positive after costs
- max drawdown and concentration must be acceptable
- every analysed candidate must have an artifact
- runbooks must be current
- a separate risk guardian process must exist outside strategy code
- `LIVE_TRADING_ENABLED` must remain disabled until a reviewed live implementation exists
