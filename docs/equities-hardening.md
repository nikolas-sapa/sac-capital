# Equities Hardening Runbook

This system is paper-only. `LIVE_TRADING_ENABLED` is a fuse and must remain false; there is no live-trading implementation path.

## Safe Modes

- `--no-analyse`: runs mark-to-market, screens, macro checks, relative-strength evidence, and exits before LLM analysis.
- `--mark-only`: marks open positions and checks exits only.
- `--reconcile-only`: reconciles Alpaca paper orders without running screens or analysis.
- `--dry-run`: screens, analyses, and risk-approves, but does not write ledger entries, forward-paper entries, or broker orders.

## Required Verification

Run the full suite before changing scheduling, execution provider settings, or risk limits:

```sh
./.venv/bin/python -m pytest
```

Run the equity-focused regression suite after equity changes:

```sh
./.venv/bin/python -m pytest tests/equities tests/test_equity_ledger.py tests/test_runner_equities_reconcile_cli.py tests/test_prices.py tests/test_fundamentals_enriched.py tests/test_macro_regime.py
```

## Operator Commands

Screen without LLM calls:

```sh
./.venv/bin/python runner_equities.py --no-analyse
```

Mark positions and exits only:

```sh
./.venv/bin/python runner_equities.py --mark-only
```

Reconcile Alpaca paper order state:

```sh
./.venv/bin/python runner_equities.py --reconcile-only
```

Run a no-write end-to-end pass:

```sh
./.venv/bin/python runner_equities.py --dry-run
```

Replay stored research artifacts:

```sh
./.venv/bin/python -m equities.eval.report --validation-start 2026-01-01
```

## What To Check Before Alpaca Paper

- `EXECUTION_PROVIDER=alpaca_paper`.
- `ALPACA_PAPER=true`.
- `ALPACA_BASE_URL=https://paper-api.alpaca.markets`.
- Alpaca API credentials are paper credentials.
- `LIVE_TRADING_ENABLED=false`.
- `MAX_ORDER_USD`, `MAX_DAILY_ORDER_COUNT`, and equity risk fields are deliberately small.
- `./.venv/bin/python runner_equities.py --dry-run` completes with a run summary.
- `./.venv/bin/python runner_equities.py --reconcile-only` completes without changing strategy state.

## Alpaca Paper Order Discipline

- Buy orders use deterministic `client_order_id` values derived from ticker, side, entry, stop, target, size, sleeve, and catalyst.
- Reruns skip an active ledger row with the same `broker_client_order_id`.
- Buy orders check Alpaca paper account state and buying power before submission.
- Buy orders enforce the local `MAX_ORDER_USD` notional guard before submission.
- Buy orders are submitted as day limit orders at the recommendation entry price.
- Submitted orders are recorded as `submitted`, not as filled positions.
- Partial fills are recorded as `partially_filled` with broker filled quantity and average fill price.
- Filled orders are reconciled to `open` with actual `filled_avg_price`.
- Unfilled terminal broker statuses are preserved as `canceled`, `expired`, or `rejected`.
- Forward-paper entries are not recorded for submitted broker orders that have not filled.

## Failure Modes

- Missing, zero, NaN, non-finite, or stale prices reject before the LLM analyst prompt.
- Invalid LLM trade geometry rejects before a `Recommendation` exists.
- The runner passes current equity, same-day realized PnL, sector lookup, and configured caps into the risk kernel.
- Provider calls log source, ticker, error, and duration where the local provider exposes those details.
- The run summary prints stage outcomes, elapsed time, provider failures, LLM failures, and exit reason.

## Evidence Trail

Analysed swing candidates append JSONL artifacts to:

```sh
data/research_artifacts.jsonl
```

Each artifact records ticker, as-of time, candidate evidence, source hashes, prompt hash, model, raw output, parsed output, decision, confidence, and rejection reason when applicable.

## Before Live Trading Exists

All of the following must be true before any separate live-trading design is considered:

- Alpaca paper execution has idempotent order submission and reconciled final fill state.
- Ledger states distinguish submitted, partially filled, filled, canceled, rejected, void, open, and closed.
- Evaluation reports show enough closed validation trades, positive expectancy, controlled drawdown, and acceptable concentration.
- Research artifacts are available for every analysed candidate.
- Runbooks and rollback procedures are current.
- A separate risk guardian process exists outside strategy code.
- The live-trading fuse remains disabled until a new reviewed implementation is explicitly built.
