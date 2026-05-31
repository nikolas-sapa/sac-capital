# Foundation (Shared Platform) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
> **Status:** DRAFT — pending grill-me.

**Goal:** Build the shared platform (CLOB connectivity, domain types, Kelly sizing, Bayesian engine, paper executor, ledger, alerts, runner) that all three bots plug into.

**Architecture:** A `core/` package exposing protocols (`Strategy`, `Executor`) and engines. Bots are plugins that implement `Strategy`. The runner loads enabled strategies, fetches markets, collects signals, sizes via Kelly, executes via the paper executor, and records to a ledger. No live trading exists.

**Tech Stack:** Python 3.12, `uv`, `websockets`, `httpx`, `pydantic`/`pydantic-settings`, `aiogram`, `pytest`, `pandas`.

---

### Task 1: Repo scaffold + tooling

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `core/__init__.py`, `tests/__init__.py`

- [ ] **Step 1:** `uv init`, add deps: `websockets httpx pydantic pydantic-settings aiogram pandas pytest pytest-asyncio`.
- [ ] **Step 2:** Write `.gitignore` (`.venv`, `__pycache__`, `.env`, `*.csv`, `data/`, `*.db`).
- [ ] **Step 3:** Write `.env.example` with `TELEGRAM_BOT_TOKEN=`, `TELEGRAM_CHAT_ID=`, `ANTHROPIC_API_KEY=`, `BANKROLL_USD=1000`, `KELLY_FRACTION=0.5`, `MAX_POSITION_PCT=0.02`.
- [ ] **Step 4:** Verify `uv run python -c "import websockets, httpx, pydantic, aiogram, pandas"` exits 0.
- [ ] **Step 5:** Commit `chore: scaffold polymarket-bot monorepo`.

---

### Task 2: Config loader (TDD)

**Files:**
- Create: `core/config.py`, `tests/test_config.py`

- [ ] **Step 1: Failing test** — assert `load_config()` reads `BANKROLL_USD`, `KELLY_FRACTION`, `MAX_POSITION_PCT` from env into a typed `Settings` object with correct defaults.
- [ ] **Step 2:** Run, expect fail (no module).
- [ ] **Step 3:** Implement `Settings(BaseSettings)` with the fields from `.env.example` and `load_config()`.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): typed config loader`.

---

### Task 3: Domain types (TDD)

**Files:**
- Create: `core/markets.py`, `tests/test_markets.py`

- [ ] **Step 1: Failing test** — construct `Outcome`, `Market`; assert frozen, assert a helper `Market.outcome_by_token(token_id)` returns the right outcome and raises on miss.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement `Outcome`, `Market` dataclasses (exact signatures from SPEC) + `outcome_by_token`.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): market domain types`.

---

### Task 4: Kelly sizing engine (TDD)

**Files:**
- Create: `core/sizing/kelly.py`, `tests/test_kelly.py`

- [ ] **Step 1: Failing test** with known values:
```python
# Binary market: pay `price` per share, share pays 1.0 if correct.
# b = (1-price)/price, q = 1-p. f* = (b*p - q)/b, then * frac.
def test_kelly_positive_edge():
    # p=0.6, price=0.5 -> b=1.0, full kelly = (1*0.6-0.4)/1 = 0.2; half = 0.1
    assert abs(kelly_fraction(0.6, 0.5, frac=0.5) - 0.1) < 1e-9
def test_kelly_no_edge_returns_zero():
    assert kelly_fraction(0.5, 0.5) == 0.0
def test_kelly_negative_edge_clamped_zero():
    assert kelly_fraction(0.4, 0.5) == 0.0
```
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement:
```python
def kelly_fraction(p: float, price: float, frac: float = 0.5) -> float:
    if not (0 < price < 1) or not (0 <= p <= 1):
        return 0.0
    b = (1 - price) / price
    q = 1 - p
    f = (b * p - q) / b
    return max(0.0, f * frac)
```
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): fractional kelly sizing`.

---

### Task 5: Bayesian shock-update engine (TDD)

**Files:**
- Create: `core/probability/bayes.py`, `tests/test_bayes.py`

- [ ] **Step 1: Failing test** — `posterior(prior, likelihood_if_true, likelihood_if_false)` returns `P(H|D)` via Bayes; verify a known case. Add `is_shock(prev_price, new_price, seconds, pct=0.08, window=60)` returns True when move >8% within 60s.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement Bayes update + `is_shock` helper.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): bayesian shock-update engine`.

---

### Task 6: CLOB REST client for market metadata (TDD with recorded fixture)

**Files:**
- Create: `core/clob/rest.py`, `tests/test_rest.py`, `tests/fixtures/gamma_market.json`

- [ ] **Step 1:** Save one real response from `https://gamma-api.polymarket.com/markets?limit=1&active=true` as a fixture.
- [ ] **Step 2: Failing test** — `parse_market(json)` maps gamma JSON → `Market` with outcomes and `end_date` parsed to UTC datetime.
- [ ] **Step 3:** Run, expect fail.
- [ ] **Step 4:** Implement `fetch_markets()` (httpx, async) + `parse_market()`. Test only `parse_market` against the fixture (no network in tests).
- [ ] **Step 5:** Run, expect pass.
- [ ] **Step 6:** Commit `feat(core): gamma-api market metadata client`.

---

### Task 7: Raw CLOB websocket client (the hot path)

**Files:**
- Create: `core/clob/client.py`, `tests/test_clob_client.py`

- [ ] **Step 1: Failing test** — feed a captured `book` message dict into `_apply_book_message(state, msg)` and assert it builds an `OrderBook` with sorted bids/asks and a `best_bid`/`best_ask`. (Pure-function test, no socket.)
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement:
  - `OrderBook` dataclass (`bids`, `asks`, `best_bid`, `best_ask`).
  - `_apply_book_message` pure function (parse + update).
  - `class ClobWebsocket` with `async def stream(token_ids: list[str])` that connects to `wss://ws-subscribe.clob.polymarket.com/ws/market`, subscribes, and yields `OrderBook` updates. Auto-reconnect with backoff.
- [ ] **Step 4:** Run unit test, expect pass.
- [ ] **Step 5: Manual integration check** — `uv run python -m core.clob.client <token_id>` prints live top-of-book for ~10s. Document expected output in the task.
- [ ] **Step 6:** Commit `feat(core): raw CLOB websocket client with reconnect`.

---

### Task 8: Strategy + Executor protocols + Signal/Fill types (TDD)

**Files:**
- Create: `core/strategy.py`, `core/execution/base.py`, `tests/test_protocols.py`

- [ ] **Step 1: Failing test** — define a dummy strategy/executor in the test implementing the protocols; assert `isinstance`-via-Protocol structural checks and that `Signal`/`Fill` construct with SPEC fields.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement `Signal`, `Strategy` (Protocol), `Fill`, `Executor` (Protocol) exactly per SPEC.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): strategy and executor protocols`.

---

### Task 9: Ledger (CSV + sqlite) (TDD)

**Files:**
- Create: `core/ledger.py`, `tests/test_ledger.py`

- [ ] **Step 1: Failing test** — `Ledger(path).record(fill)` appends a row; `Ledger.open_positions()` and `Ledger.pnl()` compute correctly after a resolve event.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement `Ledger` writing fills to CSV + a sqlite table; `record`, `resolve(condition_id, winning_token_id)`, `pnl()`, `open_positions()`.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): trade ledger with pnl`.

---

### Task 10: Paper executor (TDD)

**Files:**
- Create: `core/execution/paper.py`, `tests/test_paper.py`

- [ ] **Step 1: Failing test** — `PaperExecutor(ledger).place(signal, stake)` returns a `Fill` with `mode="paper"`, `shares = stake/avg_price`, and applies a configurable slippage + Polymarket fee model. Verify it writes to the ledger.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement `PaperExecutor`: fill at `ask * (1 + slippage)`, record fee, write `Fill` to ledger.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): paper executor with slippage/fee model`.

---

### Task 11: Telegram alerts (TDD with mock)

**Files:**
- Create: `core/alerts/telegram.py`, `tests/test_telegram.py`

- [ ] **Step 1: Failing test** — `TelegramAlerts(token, chat).format_fill(fill)` returns expected message string; sending is mocked.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement `TelegramAlerts.send(text)` (aiogram) + `format_fill`/`format_error`.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): telegram alert sink`.

---

### Task 12: Runner end-to-end with dummy strategy (TDD + manual)

**Files:**
- Create: `runner.py`, `strategies/dummy.py`, `tests/test_runner.py`

- [ ] **Step 1: Failing test** — runner with a dummy strategy that always signals on a fake market produces exactly one paper fill in the ledger; respects `MAX_POSITION_PCT` cap.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement `runner.py`: load config, fetch markets, run enabled strategies' `scan()`, size each signal via `kelly_fraction` (clamped to `MAX_POSITION_PCT * bankroll`), execute via `PaperExecutor`, alert. Dummy strategy in `strategies/dummy.py`.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5: Manual check** — `uv run python runner.py --strategy dummy` runs one loop against live gamma markets, logs a paper fill, fires a Telegram alert.
- [ ] **Step 6:** Commit `feat: end-to-end paper-trading runner`.

---

### Task 13: Resolution poller — closes the paper-PnL loop (TDD)

**Files:**
- Create: `core/resolution.py`, `tests/test_resolution.py`

- [ ] **Step 1: Failing test** — `resolve_open_positions(ledger, fetch_fn)` takes open positions, looks up each market's resolved outcome via an injected `fetch_fn` (mocked), and calls `ledger.resolve(condition_id, winning_token_id)` for any that resolved; leaves unresolved ones untouched.
- [ ] **Step 2:** Run, expect fail.
- [ ] **Step 3:** Implement `resolve_open_positions` + a real `fetch_resolution(condition_id)` hitting gamma-api (`closed`/`resolved` fields). Parsing tested against a fixture; network not in tests.
- [ ] **Step 4:** Run, expect pass.
- [ ] **Step 5:** Commit `feat(core): nightly resolution poller for paper pnl`.

---

### Task 14: launchd scheduling (manual)

**Files:**
- Create: `deploy/com.polymarketbot.runner.plist`, `deploy/com.polymarketbot.resolve.plist`, `deploy/README.md`

- [ ] **Step 1:** Write a launchd plist that runs `runner.py` on the scan interval and a second that runs the resolution poller nightly (~02:00). (macOS equivalent of the playbook's systemd/cron.)
- [ ] **Step 2:** Write `deploy/README.md` with `launchctl load` instructions and a note that VPS/systemd equivalents come at go-live, NOT Hugging Face (ephemeral storage wipes the ledger).
- [ ] **Step 3: Manual** — load the agents, confirm a scan fires and a paper fill lands in the ledger unattended.
- [ ] **Step 4:** Commit `chore: launchd agents for runner + nightly resolution`.

---

## Self-Review Checklist
- [ ] Every SPEC shared contract (`Outcome`, `Market`, `Signal`, `Strategy`, `Fill`, `Executor`, `kelly_fraction`) is implemented in a task.
- [ ] No live-execution code path exists.
- [ ] CLOB websocket uses raw `websockets`, not a wrapper, in the hot path.
- [ ] Tests never hit the network (fixtures for parsing, mocks for sending).
- [ ] Resolution loop exists (Task 13) — paper PnL is real, not assumed.
- [ ] Scheduling is launchd (Mac), not systemd/HF, for the paper phase (Task 14).
