# sapa_fund Hardening + Alpha Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 5 critical trade-safety bugs, secure the frontend API + secrets, add look-ahead validation, then layer the top strategy improvements (technicals in screen, sizing debate, vol-targeting A/B).

**Architecture:** Surgical fixes to existing modules (risk kernel, equity ledger, runner) with one test per fix; new `equities/risk/state.py` for persisted kernel state; Vercel API middleware for auth; decision-cutoff tagging in artifact exporter. No restructuring of runner_equities.py in this plan (separate refactor plan later).

**Tech Stack:** Python 3.12 + uv + pytest + SQLite · Vite/React + Vercel serverless (frontend/api) · Alpaca paper API.

## Global Constraints

- Paper trading only — no live brokerage writes.
- Run tests with: `set -a; source .env; set +a; uv run pytest <path> -v` (env vars needed by conftest).
- npm only for frontend (never yarn/pnpm/bun).
- Never commit `.env`. Never echo secret values in code, logs, or commits.
- All ledger changes must keep SQLite as source of truth; CSV is a mirror.
- Commit after each task. Branch strategy: Phases 0–2 on `hardening-2026-07` (one PR); Phase 3 on `strategy-2026-07` (separate PR) so safety fixes aren't held up by feature review.

---

## Phase 0 — Secrets rotation (manual, do first)

### Task 0: Rotate leaked secrets

**Files:** none (external consoles) + `.env` (values only)

- [ ] **Step 1:** Rotate Mantle private key: create new wallet, move any funds, update `MANTLE_PRIVATE_KEY` in `.env`. If the contract is owner-gated, transfer ownership or redeploy pointing at new signer.
- [ ] **Step 2:** Rotate Telegram bot token via BotFather `/revoke`, update `TELEGRAM_BOT_TOKEN` in `.env`.
- [ ] **Step 3:** Verify nothing references old values: `grep -rn "0x7932a194\|8996794782" --include="*.py" --include="*.ts" --include="*.md" ~/sapa_fund` → expect no hits outside `.env` history.

---

## Phase 1 — Trade-safety criticals

### Task 1: Persist risk-kernel high-water mark across runs

**Files:**
- Create: `equities/risk/state.py`
- Modify: `equities/risk/kernel.py:52-77` (init), `runner_equities.py` (kernel construction site, ~line 894)
- Test: `tests/equities/test_kernel_state.py`

**Interfaces:**
- Produces: `load_kernel_state(path: Path) -> dict` and `save_kernel_state(path: Path, hwm: float, halted: bool) -> None`; `RiskKernel(..., state_path: Path | None = None)` loads/saves hwm + halted flag.

- [ ] **Step 1: Write the failing test**

```python
# tests/equities/test_kernel_state.py
from pathlib import Path
from equities.risk.kernel import RiskKernel

def test_high_water_mark_survives_restart(tmp_path: Path):
    state = tmp_path / "kernel_state.json"
    k1 = RiskKernel(capital=10_000, state_path=state)
    # simulate equity climbing to 12k via an approve() drawdown check
    class Rec:  # minimal stub
        entry = 100.0; stop = 95.0; size_pct = 0.02; sleeve = None
        class instrument: ticker = "TEST"
    k1.approve(Rec(), [], current_equity=12_000)
    k2 = RiskKernel(capital=10_000, state_path=state)
    assert k2._high_water_mark == 12_000

def test_halted_flag_survives_restart(tmp_path: Path):
    state = tmp_path / "kernel_state.json"
    k1 = RiskKernel(capital=10_000, state_path=state)
    class Rec:
        entry = 100.0; stop = 95.0; size_pct = 0.02; sleeve = None
        class instrument: ticker = "TEST"
    k1.approve(Rec(), [], current_equity=12_000)   # sets hwm
    k1.approve(Rec(), [], current_equity=10_000)   # 16.7% drawdown -> halt
    k2 = RiskKernel(capital=10_000, state_path=state)
    sized = k2.approve(Rec(), [], current_equity=10_000)
    assert not sized.approved and "circuit_breaker" in sized.rejection_reason
```

- [ ] **Step 2:** Run: `uv run pytest tests/equities/test_kernel_state.py -v` → FAIL (`state_path` unexpected kwarg).
- [ ] **Step 3: Implement**

```python
# equities/risk/state.py
import json
from pathlib import Path

def load_kernel_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

def save_kernel_state(path: Path, hwm: float, halted: bool) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"high_water_mark": hwm, "halted": halted}))
    tmp.replace(path)
```

In `kernel.py.__init__` add `state_path: Path | None = None` param; after existing field init:

```python
        self._state_path = state_path
        if state_path is not None:
            from equities.risk.state import load_kernel_state
            saved = load_kernel_state(state_path)
            if float(saved.get("capital", capital)) == capital:
                self._high_water_mark = max(capital, float(saved.get("high_water_mark", capital)))
                self._halted = bool(saved.get("halted", False))
            # else: bankroll changed in config -> stale hwm/halt discarded, fresh baseline
```

`save_kernel_state` also stores `capital` (add param). Note: kernel state persists in `--dry-run` too — approve() runs there and equity is real, so a persisted halt reflects real drawdown; this is intended.

In `approve()` after any mutation of `_high_water_mark` or `_halted` (lines 105 and 108):

```python
        if self._state_path is not None:
            from equities.risk.state import save_kernel_state
            save_kernel_state(self._state_path, self._high_water_mark, self._halted)
```

In `runner_equities.py` where the kernel is constructed, pass `state_path=Path("data/kernel_state.json")`.

- [ ] **Step 4:** Run tests → PASS. Run full suite: `uv run pytest tests/equities -v`.
- [ ] **Step 5:** Commit: `fix(risk): persist high-water mark and halt flag across runner restarts`

---

### Task 2: Deduct pending order notional from current equity

**Files:**
- Modify: `runner_equities.py:925-932`
- Test: `tests/equities/test_pending_notional.py`

**Interfaces:**
- Produces: `EquityLedger.pending_notional() -> float` on `equities/ledger_equity.py` (sums `shares*entry_price` for `status='submitted'`).

- [ ] **Step 1: Write the failing test**

```python
# tests/equities/test_pending_notional.py
def test_pending_notional_sums_submitted_positions(equity_ledger_factory):
    ledger = equity_ledger_factory()  # reuse existing test fixture pattern from tests/equities/
    # open one submitted and one open position via the same helper other ledger tests use
    _open(ledger, ticker="AAA", shares=10, entry=100.0, status="submitted")
    _open(ledger, ticker="BBB", shares=5, entry=50.0, status="open")
    assert ledger.pending_notional() == 1000.0
```

(Adapt `_open`/fixture to the existing conventions in `tests/equities/test_alpaca_reconciler.py` — copy its ledger-setup helper.)

- [ ] **Step 2:** Run → FAIL (`pending_notional` missing).
- [ ] **Step 3: Implement** in `equities/ledger_equity.py` next to `portfolio_stats()`:

```python
    def pending_notional(self) -> float:
        # ponytail: reserves fully-unfilled orders only; the unfilled remainder of a
        # partially_filled order is not reserved — add remainder tracking if partial
        # fills become common at this order size.
        row = self._con.execute(
            "SELECT COALESCE(SUM(shares * entry_price), 0.0) FROM positions "
            "WHERE status = 'submitted'"
        ).fetchone()[0]
        return float(row)
```

In `runner_equities.py:927-931`:

```python
        current_equity = (
            settings.bankroll_usd
            + float(portfolio_stats.get("realized_pnl", 0.0))
            + float(portfolio_stats.get("unrealized_pnl", 0.0))
        )
        deployable_equity = current_equity - equity_ledger.pending_notional()
```

and pass `current_equity=deployable_equity` to `kernel.approve(...)` at line 939.

- [ ] **Step 4:** Run tests → PASS.
- [ ] **Step 5:** Commit: `fix(risk): reserve pending order notional before sizing new trades`

---

### Task 3: Block resubmission of any known client_order_id (date-scoped IDs)

**Files:**
- Modify: `runner_equities.py:983-991`, `equities/execution/alpaca.py:203-217` (`client_order_id_for`)
- Test: `tests/equities/test_duplicate_order_guard.py`

**Rationale (from grill):** `client_order_id_for` hashes ticker/entry/stop/TP/shares/catalyst with no date — blocking any existing ID forever would also block a legitimate identical re-entry weeks later. Fix both: (a) add the UTC date to the hash payload so each day gets fresh IDs, (b) block on ANY existing row for the ID (covers the rejected-order resubmission bug within a day).

- [ ] **Step 1: Write the failing test** — unit-test the guard predicate, extracted as a function:

```python
# tests/equities/test_duplicate_order_guard.py
from runner_equities import _should_skip_duplicate

def test_rejected_order_blocks_resubmission():
    assert _should_skip_duplicate({"status": "rejected"}) is True

def test_active_order_blocks_resubmission():
    assert _should_skip_duplicate({"status": "submitted"}) is True

def test_no_existing_order_allows_submission():
    assert _should_skip_duplicate(None) is False
```

- [ ] **Step 2:** Run → FAIL (function missing).
- [ ] **Step 3: Implement** in `runner_equities.py` near `_has_active_broker_order`:

```python
def _should_skip_duplicate(existing_order: dict | None) -> bool:
    # ponytail: any prior row with this client_order_id blocks resubmission;
    # Alpaca idempotency on reused IDs after rejection is undefined.
    return existing_order is not None
```

Replace the check at line 986: `if _should_skip_duplicate(existing_order):`.

And in `equities/execution/alpaca.py:205` add the UTC date to the payload so IDs are day-scoped:

```python
    payload = "|".join([
        "equity",
        datetime.now(tz=timezone.utc).date().isoformat(),  # day-scoped idempotency
        recommendation.side,
        ...  # existing fields unchanged
    ])
```

Add a test: `test_client_order_id_changes_across_days` (monkeypatch date, assert different IDs).

- [ ] **Step 4:** Run tests → PASS.
- [ ] **Step 5:** Commit: `fix(execution): never reuse a client_order_id, even after rejection`

---

### Task 4: Atomic CSV mirror writes

**Files:**
- Modify: `equities/ledger_equity.py:304-312`, `core/ledger.py:212-219` (same pattern)
- Test: `tests/equities/test_csv_atomic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/equities/test_csv_atomic.py
def test_rewrite_csv_leaves_no_tmp_and_valid_csv(equity_ledger_factory, tmp_path):
    ledger = equity_ledger_factory(csv_path=tmp_path / "positions.csv")
    _open(ledger, ticker="AAA", shares=1, entry=10.0, status="open")
    assert not (tmp_path / "positions.csv.tmp").exists()
    import csv
    rows = list(csv.DictReader(open(tmp_path / "positions.csv")))
    assert rows[0]["ticker"] == "AAA"
```

- [ ] **Step 2:** Run → currently PASSES for content but write is non-atomic; assert on tmp file makes intent explicit. To force a real failing state first, temporarily assert `_rewrite_csv` uses replace — instead simply proceed: this is a rare acceptable "characterization then refactor" case.
- [ ] **Step 3: Implement** in both files:

```python
    def _rewrite_csv(self) -> None:
        rows = self._con.execute("SELECT * FROM positions ORDER BY id").fetchall()
        tmp = self._csv_path.with_suffix(self._csv_path.suffix + ".tmp")
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            w.writeheader()
            for row in rows:
                d = dict(row)
                w.writerow({k: d.get(k, "") for k in _CSV_HEADERS})
        tmp.replace(self._csv_path)  # atomic on POSIX
```

(`self._csv_path` must be a `Path`; it already is — verify at init.)

- [ ] **Step 4:** Run: `uv run pytest tests/equities -v` → PASS.
- [ ] **Step 5:** Commit: `fix(ledger): atomic temp+rename CSV mirror writes`

---

### Task 5: Explicit Alpaca order-status mapping

**Files:**
- Modify: `runner_equities.py:1006-1008`
- Test: `tests/equities/test_order_status_mapping.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/equities/test_order_status_mapping.py
from runner_equities import _local_status_for

def test_known_statuses():
    assert _local_status_for("filled") == "open"
    assert _local_status_for("partially_filled") == "partially_filled"
    assert _local_status_for("new") == "submitted"
    assert _local_status_for("accepted") == "submitted"

def test_terminal_failures_map_to_rejected():
    for s in ("rejected", "canceled", "cancelled", "expired", "suspended", "stopped"):
        assert _local_status_for(s) == "rejected"

def test_unknown_status_maps_to_submitted_with_warning(capsys):
    assert _local_status_for("weird_new_status") == "submitted"
    assert "unknown broker status" in capsys.readouterr().out
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** in `runner_equities.py`:

```python
_TERMINAL_FAILURE_STATUSES = {"rejected", "canceled", "cancelled", "expired", "suspended", "stopped"}

def _local_status_for(broker_status: str) -> str:
    if broker_status == "filled":
        return "open"
    if broker_status == "partially_filled":
        return "partially_filled"
    if broker_status in _TERMINAL_FAILURE_STATUSES:
        return "rejected"
    if broker_status not in {"new", "accepted", "pending_new", "accepted_for_bidding"}:
        print(f"  WARNING unknown broker status '{broker_status}', treating as submitted")
    return "submitted"
```

Replace lines 1006-1008 with `local_status = _local_status_for(order.status)`. When `local_status == "rejected"`, skip `open_position` and record a rejection artifact instead (mirror the `alpaca_error` branch at line 1000-1005).

- [ ] **Step 4:** Run tests → PASS.
- [ ] **Step 5:** Commit: `fix(execution): explicit broker status mapping; rejected orders no longer recorded as pending`

---

### Task 6: Daily order cap — decide + document semantics

**Files:**
- Modify: `equities/ledger_equity.py:204-212` (only if decision = exclude voided/rejected)
- Test: extend `tests/equities/` existing cap test

- [ ] **Step 1:** Decision (owner call, default proposed): daily cap counts *orders submitted today regardless of later closure* (current behavior is correct for that), but **excludes** `status IN ('void','rejected')` so failed submissions don't consume the cap.
- [ ] **Step 2:** Test:

```python
def test_rejected_orders_do_not_consume_daily_cap(equity_ledger_factory):
    ledger = equity_ledger_factory()
    _open(ledger, ticker="AAA", status="rejected", broker_order_id="x1")
    _open(ledger, ticker="BBB", status="open", broker_order_id="x2")
    assert ledger.broker_orders_opened_on(today_iso()) == 1
```

- [ ] **Step 3: Implement:** add `"AND status NOT IN ('void','rejected') "` to the WHERE clause in `broker_orders_opened_on`.
- [ ] **Step 4:** Run tests → PASS. Commit: `fix(ledger): rejected/void orders no longer consume daily order cap`

---

## Phase 2 — API security (frontend/api)

### Task 7: Shared auth + error sanitization middleware for Vercel routes

**Files:**
- Create: `frontend/api/_lib/guard.ts`
- Modify: `frontend/api/positions.ts`, `frontend/api/portfolio-history.ts`, `frontend/api/stock-bars.ts`
- Test: manual curl verification (no test harness for Vercel functions in repo)

**Interfaces:**
- Produces: `withGuard(handler)` wrapper — checks `Authorization: Bearer <DASHBOARD_API_TOKEN>`, returns 401/403, catches upstream errors and returns generic message while logging details server-side.

- [ ] **Step 1: Implement guard**

```typescript
// frontend/api/_lib/guard.ts
import type { VercelRequest, VercelResponse } from "@vercel/node";

type Handler = (req: VercelRequest, res: VercelResponse) => Promise<void> | void;

export function withGuard(handler: Handler): Handler {
  return async (req, res) => {
    const token = process.env.DASHBOARD_API_TOKEN;
    if (!token) {
      console.error("DASHBOARD_API_TOKEN not configured");
      return void res.status(500).json({ error: "Server misconfigured" });
    }
    const auth = req.headers.authorization ?? "";
    if (auth !== `Bearer ${token}`) {
      return void res.status(401).json({ error: "Unauthorized" });
    }
    try {
      await handler(req, res);
    } catch (err) {
      console.error("API handler error:", err);
      if (!res.headersSent) res.status(502).json({ error: "Upstream request failed" });
    }
  };
}

export function upstreamError(res: VercelResponse, status: number, detail: string): void {
  console.error(`Upstream error ${status}:`, detail); // server logs only
  res.status(status).json({ error: "Failed to fetch market data" });
}
```

- [ ] **Step 2:** In each of the 3 routes: wrap default export `export default withGuard(handler)`; replace `return res.status(response.status).json({ error: text })` with `return upstreamError(res, response.status, text)`. Also set `res.setHeader("Cache-Control", "private, no-store")` on positions + portfolio-history.
- [ ] **Step 3:** **DECIDED (grill):** dashboard stays public (hackathon demo; a `VITE_*` token would be visible to visitors anyway). Skip the `withGuard` auth wrapper on routes — keep only the error-sanitization catch, `Cache-Control: private, no-store` on positions/portfolio-history, and `period` validation. Keep `guard.ts`'s `upstreamError` helper; drop the token check. If the fund goes beyond demo, revisit with real auth (signed sessions), not a static token.
- [ ] **Step 4:** Deploy preview (`vercel deploy` from frontend/), curl each route with/without header, verify behavior. Commit: `sec(api): sanitize upstream errors, no-store cache headers on account routes`
- [ ] **Step 5:** Validate `period` param in portfolio-history: return 400 on unknown values (code from security report Finding 5).

---

## Phase 3 — Strategy improvements (research-driven)

### Task 8: Point-in-time data cutoff tagging + leak check

**Files:**
- Modify: decision artifact exporter (`equities/` artifact_store / `risk_decision_artifact` producer), congressional + supplier data providers
- Test: `tests/equities/test_pit_cutoff.py`

- [ ] **Step 1:** Every decision artifact gets `data_cutoff_utc` (run start time) and each signal source reports `as_of_utc` (publication/disclosure timestamp of the newest datum used).
- [ ] **Step 2: Test:**

```python
def test_decision_rejects_future_data():
    from equities.pit import assert_point_in_time
    cutoff = "2026-07-03T00:00:00Z"
    with pytest.raises(LookAheadError):
        assert_point_in_time(cutoff, sources=[{"name": "senate", "as_of_utc": "2026-07-04T00:00:00Z"}])
```

- [ ] **Step 3: Implement** `equities/pit.py` with `LookAheadError` and `assert_point_in_time(cutoff, sources)` (simple ISO-timestamp comparison loop). Call it in the analyst stage before `kernel.approve`, passing each provider's `as_of_utc`. Providers that can't produce a timestamp report `as_of_utc=None` → logged warning (not fatal) so rollout is incremental.
- [ ] **Step 4:** Commit: `feat(research): point-in-time cutoff tagging + look-ahead guard`

### Task 9: Technical indicators in the screen + analyst prompt

**Files:**
- Create: `equities/data/technicals.py`
- Modify: analyst prompt builder in `equities/analysis/analyst.py`, screen stage in `runner_equities.py`
- Test: `tests/equities/test_technicals.py`

- [ ] **Step 1:** `compute_technicals(bars: list[Bar]) -> dict` returning `{"rsi_14": float, "macd_hist": float, "mom_20d_pct": float, "vol_20d_ann_pct": float}` — pure functions on the price bars already fetched for marking (reuse existing price provider, no new dependency).
- [ ] **Step 2:** Test with a fixed 30-bar synthetic series and hand-computed RSI/MACD expectations.
- [ ] **Step 3:** Inject one line into the Sonnet bull-thesis and challenger prompts: `Technicals: RSI14={..} MACD_hist={..} 20d momentum={..}% 20d vol={..}%. Flag any divergence between thesis and price action.` Haiku pre-filter gets momentum only.
- [ ] **Step 4:** Commit: `feat(analysis): technical indicator context in screen + analyst prompts`

### Task 10: Sizing debate — challenger can push back on size

**Files:**
- Modify: `equities/analysis/analyst.py` (challenger prompt + response schema)
- Test: `tests/equities/test_sizing_debate.py`

- [ ] **Step 1:** Extend challenger output schema with `size_verdict: "full" | "half" | "skip"` + `size_rationale: str`. Prompt addition: "Given drawdown headroom {dd_headroom_pct}%, sector concentration {sector_pct}%, and vol regime {vol_20d}%, is the proposed 2% risk justified? Answer full/half/skip."
- [ ] **Step 2:** In runner, apply: `half` → multiply `rec.size_pct` by 0.5 before `kernel.approve`; `skip` → reject with artifact `stage="sizing_debate"`. Kernel caps still apply after.
- [ ] **Step 3:** Test: parse fixture challenger responses for each verdict, assert size adjustment applied.
- [ ] **Step 4:** Commit: `feat(analysis): challenger debates position size, not just thesis`

### Task 11: Vol-targeting vs fractional-Kelly A/B (paper, shadow mode)

**Files:**
- Create: `equities/risk/vol_target.py`, `scripts/sizing_ab_report.py`
- Test: `tests/equities/test_vol_target.py`

- [ ] **Step 1:** `vol_target_shares(entry, vol_20d_ann_pct, capital, target_vol_pct=20.0) -> float`. Shadow only: at approve time, compute both sizes, log both in the decision artifact (`sizing={"kelly_shares": .., "voltarget_shares": ..}`); execution continues to use the kernel's size.
- [ ] **Step 2:** `scripts/sizing_ab_report.py` replays closed trades from the ledger applying each sizing to compute hypothetical PnL/Sharpe/max-DD; prints comparison table.
- [ ] **Step 3:** Test the sizing function on fixed inputs; test report math on a 3-trade fixture ledger.
- [ ] **Step 4:** Commit: `feat(risk): shadow vol-targeting sizing + A/B report`. Review after ≥30 closed trades before switching.

### Task 12: Signal-decay memory table

**Files:**
- Create: `equities/signal_stats.py`
- Modify: analyst prompt builder; position close path (record signal_class on positions if not already)
- Test: `tests/equities/test_signal_stats.py`

- [ ] **Step 1:** SQLite table `signal_stats(signal_class TEXT, regime TEXT, window_end TEXT, trades INT, win_rate REAL)` in equity.db, rebuilt by `update_signal_stats(ledger)` from closed positions (positions need a `signal_class` column — add via `_ensure_column`). Note: historical positions have no signal_class, so stats accumulate from deployment forward — the <10-trade suppression in Step 2 covers the cold start.
- [ ] **Step 2:** Inject into thesis prompt: `Historical 30d win rate for {signal_class} in {regime}: {win_rate:.0%} over {trades} trades — weight conviction accordingly.` Suppress line when trades < 10 (insufficient sample).
- [ ] **Step 3:** Test: fixture ledger with known outcomes → expected win rates.
- [ ] **Step 4:** Commit: `feat(analysis): regime-conditional signal win-rate memory in prompts`

---

## Deferred (separate plans — do not start here)

- `runner_equities.py` decomposition (pipeline extraction, adapters, stage DAG) — after Phase 1 lands, so refactor doesn't collide with fixes.
- Frontend error-state UX + orange→blue design token fixes — small standalone PR.
- Semi-streaming congressional herd alerts, regime clustering — after signal-stats table has data.
- HIGH items: prefilter exception logging (one-line, fold into Task 9's file touch), LLM subprocess retry (tenacity wrapper), same-day loss accounting.

## Verification (end of each phase)

- Phase 1: `set -a; source .env; set +a; uv run pytest tests -v` all green; then `uv run python runner_equities.py --dry-run` completes with no new rejections of type `error`.
- Phase 2: curl matrix on preview deployment (401 without token if gated; generic error body on forced upstream failure).
- Phase 3: `--dry-run` run shows technicals + sizing verdict + PIT cutoff in decision artifacts.
