# Evidence-Based Risk Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 9 safe-to-automate upgrades from `profit-research-report.md` §5 — a real exit engine, calibration-gated sizing, honest Kelly, binding size verdicts, hard mechanical gates, the vol-target bugfix, a risk-escalation gate, 13D detection, and probe-then-pyramid — so every quantitative control that is currently prose or dead code actually executes.

**Architecture:** All changes are env-gated or additive so the pipeline's current behavior is recoverable by flag. Exit logic becomes *stateless* — an effective stop computed each night from `(entry, stop_loss, take_profit, high_water_price)` — with the ledger's new `high_water_price` column the only new state. Sizing changes flow through one seam: `RiskKernel.approve()`. Attribution (already merged, `equities/analysis/attribution.py`) is the single source of empirical win rates.

**Tech Stack:** Python 3.12, sqlite3, pydantic-settings, pytest. No new dependencies.

## Global Constraints

- Repo: `/Users/nikolassapalidis/Developer/python/sapa_fund`, branch `feat/evidence-based-risk-engine` off `main`.
- Run tests with `.venv/bin/python -m pytest` (never bare `pytest`).
- **NO `Co-Authored-By` in commits** (Vercel Hobby blocks deploys). End commit messages with:
  `Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7`
- Push the branch after each task's commit (`git push -u origin feat/evidence-based-risk-engine`).
- New config fields go in `core/config.py` (pydantic `Settings`), lowercase snake_case; env var is the uppercase of the field name. Every new behavior knob defaults listed per task — behavior-changing gates default ON only where the report marks them protective; probe-pyramid defaults OFF.
- Excluded from this plan (needs its own brainstorm + plan — strategy decision, marked HJ in report §5.8): the dynamic small/mid universe rebuild, SUE-gated PEAD, implied-move fetch, merger-arb screen.
- The paper ledger DBs (`data/equity.db`) are live state — tests must always use `tmp_path`, never touch `data/`.

---

### Task 1: Attribution band-stats API

The report's #2 fix needs a queryable "how has each confidence band actually performed" API. `attribute()` already buckets by band; expose it directly plus a size-cap helper.

**Files:**
- Modify: `equities/analysis/attribution.py` (append after `graded_lessons`, line ~132)
- Test: `tests/equities/analysis/test_attribution.py` (append)

**Interfaces:**
- Consumes: existing `attribute(db_path) -> AttributionReport`, `_conf_band(conf) -> str`, `Bucket`.
- Produces: `confidence_band_stats(db_path) -> dict[str, Bucket]` (key = band label like `"0.75-1.00"`), and `calibration_size_cap(confidence: float, db_path, min_n: int = 3, cap: float = 0.01) -> float | None` — returns `cap` when the trade's band has `n >= min_n` and `avg_pnl < 0`, else `None`. Tasks 2 and 11 import these.

- [ ] **Step 1: Write the failing tests**

Append to `tests/equities/analysis/test_attribution.py`:

```python
from equities.analysis.attribution import (
    attribute,
    calibration_size_cap,
    confidence_band_stats,
    graded_lessons,
)


def test_confidence_band_stats_keys_by_band(tmp_path):
    db = str(tmp_path / "equity.db")
    _seed(db, [
        (0.85, "equity_analyst", "Tech", "time_stop", -5.0),
        (0.80, "equity_analyst", "Tech", "time_stop", -4.0),
        (0.90, "equity_analyst", "Tech", "stop_hit", -6.0),
        (0.50, "research_static", "Tech", "target_hit", 2.0),
    ])
    stats = confidence_band_stats(db)
    assert stats["0.75-1.00"].n == 3
    assert stats["0.75-1.00"].avg_pnl < 0
    assert stats["0.00-0.60"].n == 1


def test_calibration_size_cap_fires_on_inverted_band(tmp_path):
    db = str(tmp_path / "equity.db")
    _seed(db, [
        (0.85, "equity_analyst", "Tech", "time_stop", -5.0),
        (0.80, "equity_analyst", "Tech", "time_stop", -4.0),
        (0.90, "equity_analyst", "Tech", "stop_hit", -6.0),
    ])
    # 0.82 falls in the 0.75-1.00 band: n=3, negative avg -> capped
    assert calibration_size_cap(0.82, db) == 0.01
    # 0.50 band has no data -> no cap
    assert calibration_size_cap(0.50, db) is None


def test_calibration_size_cap_respects_min_n(tmp_path):
    db = str(tmp_path / "equity.db")
    _seed(db, [(0.85, "equity_analyst", "Tech", "time_stop", -5.0)])
    assert calibration_size_cap(0.85, db, min_n=3) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/equities/analysis/test_attribution.py -q`
Expected: FAIL — `ImportError: cannot import name 'confidence_band_stats'`

- [ ] **Step 3: Implement**

Append to `equities/analysis/attribution.py`:

```python
def confidence_band_stats(db_path: str | Path = "data/equity.db") -> dict[str, "Bucket"]:
    """Realized outcome stats keyed by confidence band label."""
    report = attribute(db_path)
    return {b.label: b for b in report.buckets if b.dimension == "confidence"}


def calibration_size_cap(
    confidence: float,
    db_path: str | Path = "data/equity.db",
    min_n: int = 3,
    cap: float = 0.01,
) -> float | None:
    """Max size_pct for a trade whose confidence band has proven unprofitable.

    Returns `cap` (NIBBLE) when the band has >= min_n closed trades with a
    negative average PnL — the bot's own ledger says this band's conviction
    is miscalibrated. Returns None when there is no evidence against the band.
    """
    band = _conf_band(confidence)
    bucket = confidence_band_stats(db_path).get(band)
    if bucket is None or bucket.n < min_n:
        return None
    if bucket.avg_pnl < 0:
        return cap
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/equities/analysis/test_attribution.py -q`
Expected: all PASS (3 existing + 3 new)

- [ ] **Step 5: Commit + push**

```bash
git add equities/analysis/attribution.py tests/equities/analysis/test_attribution.py
git commit -m "feat(attribution): band-stats API + calibration size cap

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push -u origin feat/evidence-based-risk-engine
```

---

### Task 2: Calibration-gated sizing in the analyst

The 0.75+ confidence band is 0/4 for −$17.54 yet still receives the 4% AGGRESSIVE_BUILD tier (`analyst.py:265` → `_compute_build_action`). Cap any evidence-against band at NIBBLE.

**Files:**
- Modify: `equities/analysis/analyst.py` (call site at line ~265, plus new module-level function above `_compute_build_action` at line ~971)
- Test: `tests/equities/analysis/test_analyst.py` (append)

**Interfaces:**
- Consumes: `calibration_size_cap(confidence, db_path)` from Task 1.
- Produces: module-level `_apply_calibration_cap(size_pct: float, confidence: float) -> tuple[float, bool]` in `analyst.py` (returns possibly-capped size and whether cap fired). Env gate: `EQUITY_CALIBRATION_SIZING` (default `"true"`, matching the `EQUITY_MEMORY_ENABLED` pattern already in this file), db path override for tests: `EQUITY_LEDGER_PATH_FOR_CALIBRATION` (defaults `data/equity.db`).

- [ ] **Step 1: Write the failing test**

Append to `tests/equities/analysis/test_analyst.py`:

```python
def test_apply_calibration_cap_caps_inverted_band(tmp_path, monkeypatch):
    import sqlite3
    from equities.analysis.analyst import _apply_calibration_cap

    db = str(tmp_path / "equity.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE positions (confidence REAL, strategy TEXT, sector TEXT, "
        "exit_reason TEXT, realized_pnl REAL, status TEXT)"
    )
    con.executemany(
        "INSERT INTO positions VALUES (?,?,?,?,?,'closed')",
        [(0.85, "equity_analyst", "Tech", "time_stop", -5.0),
         (0.80, "equity_analyst", "Tech", "time_stop", -4.0),
         (0.90, "equity_analyst", "Tech", "stop_hit", -6.0)],
    )
    con.commit(); con.close()
    monkeypatch.setenv("EQUITY_CALIBRATION_SIZING", "true")
    monkeypatch.setenv("EQUITY_LEDGER_PATH_FOR_CALIBRATION", db)

    size, capped = _apply_calibration_cap(0.04, confidence=0.85)
    assert size == 0.01 and capped is True

    # band without adverse evidence passes through untouched
    size, capped = _apply_calibration_cap(0.02, confidence=0.55)
    assert size == 0.02 and capped is False


def test_apply_calibration_cap_disabled_by_env(monkeypatch):
    from equities.analysis.analyst import _apply_calibration_cap
    monkeypatch.setenv("EQUITY_CALIBRATION_SIZING", "false")
    size, capped = _apply_calibration_cap(0.04, confidence=0.85)
    assert size == 0.04 and capped is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/equities/analysis/test_analyst.py -q -k calibration`
Expected: FAIL — `ImportError: cannot import name '_apply_calibration_cap'`

- [ ] **Step 3: Implement**

In `equities/analysis/analyst.py`, add module-level function directly above `_compute_build_action` (line ~971):

```python
def _apply_calibration_cap(size_pct: float, confidence: float) -> tuple[float, bool]:
    """Cap size_pct at NIBBLE when this confidence band has negative realized PnL.

    The ledger is the authority on whether the analyst's conviction is
    calibrated — stated confidence never overrides measured outcomes.
    Gated by EQUITY_CALIBRATION_SIZING (default on).
    """
    if os.getenv("EQUITY_CALIBRATION_SIZING", "true").lower() not in {"1", "true", "yes", "on"}:
        return size_pct, False
    try:
        from equities.analysis.attribution import calibration_size_cap

        db_path = os.getenv("EQUITY_LEDGER_PATH_FOR_CALIBRATION", "data/equity.db")
        cap = calibration_size_cap(confidence, db_path)
    except Exception:
        return size_pct, False
    if cap is not None and size_pct > cap:
        return cap, True
    return size_pct, False
```

Then modify the call site at line ~265 — current code:

```python
            _action, size_pct = _compute_build_action(
                analyst_confidence=audited.confidence,
                consistency_penalty=0.0,  # already applied by auditor
                regime=regime,
            )
            if size_pct == 0.0:
                continue  # WAIT — skip
            final = dc_replace(audited, size_pct=size_pct)
```

becomes:

```python
            _action, size_pct = _compute_build_action(
                analyst_confidence=audited.confidence,
                consistency_penalty=0.0,  # already applied by auditor
                regime=regime,
            )
            if size_pct == 0.0:
                continue  # WAIT — skip
            size_pct, calibration_capped = _apply_calibration_cap(
                size_pct, audited.confidence
            )
            if calibration_capped:
                print(
                    f"  [CALIBRATION CAP] {audited.instrument.ticker}: "
                    f"band has negative realized PnL — size capped at {size_pct:.0%}"
                )
            final = dc_replace(audited, size_pct=size_pct)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/equities/analysis/test_analyst.py tests/equities/analysis/test_attribution.py -q`
Expected: all PASS

- [ ] **Step 5: Commit + push**

```bash
git add equities/analysis/analyst.py tests/equities/analysis/test_analyst.py
git commit -m "feat(analyst): calibration-gated sizing — ledger evidence caps inverted bands at NIBBLE

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 3: Make size_pct bind in the kernel swing branch

The challenger's `half` verdict and the build tiers change **zero swing dollars** — `kernel.approve` reads `size_pct` only in the CORE branch (`kernel.py:137-143`). Scale swing risk by `size_pct / 0.02` (0.02 = GRADUAL_BUILD baseline).

**Files:**
- Modify: `equities/risk/kernel.py` (swing sizing block, line ~179)
- Test: locate the kernel test file first: `grep -rln "RiskKernel" tests/` — append there.

**Interfaces:**
- Consumes: `Recommendation.size_pct` (0.04 / 0.02 / 0.01 from `_compute_build_action`, possibly halved by the challenger verdict).
- Produces: swing sizing uses `effective_risk_pct = self.risk_pct * (rec.size_pct / 0.02)` clamped to `[0.25 * self.risk_pct, 2.0 * self.risk_pct]`; falls back to `self.risk_pct` when `size_pct <= 0`.

- [ ] **Step 1: Write the failing test**

Append to the kernel test file (reuse its existing `RiskKernel` + swing-`Recommendation` construction helpers — copy the exact constructor calls already present in that file's other tests; if no factory fixture exists, add one mirroring them):

```python
def test_size_pct_scales_swing_risk(kernel_and_rec_factory):
    """AGGRESSIVE (0.04) sizes 2x the GRADUAL baseline (0.02); NIBBLE (0.01) sizes 0.5x."""
    kernel, make_rec = kernel_and_rec_factory  # capital=100_000, risk_pct=0.02
    rec_gradual = make_rec(entry=100.0, stop_loss=95.0, size_pct=0.02)
    rec_aggressive = make_rec(entry=100.0, stop_loss=95.0, size_pct=0.04)
    rec_nibble = make_rec(entry=100.0, stop_loss=95.0, size_pct=0.01)

    s_gradual = kernel.approve(rec_gradual, [], today_realized_loss=0.0, current_equity=100_000)
    s_aggr = kernel.approve(rec_aggressive, [], today_realized_loss=0.0, current_equity=100_000)
    s_nibble = kernel.approve(rec_nibble, [], today_realized_loss=0.0, current_equity=100_000)

    assert s_aggr.shares == pytest.approx(2.0 * s_gradual.shares, rel=1e-6)
    assert s_nibble.shares == pytest.approx(0.5 * s_gradual.shares, rel=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest <kernel test file> -q -k size_pct_scales`
Expected: FAIL — aggressive shares equal gradual shares (size_pct currently ignored)

- [ ] **Step 3: Implement**

In `equities/risk/kernel.py`, the swing sizing block (line ~179):

```python
        shares = size_shares(
            capital=self.capital,
            risk_pct=self.risk_pct,
            entry=recommendation.entry,
            stop_loss=recommendation.stop_loss,
            gap_pct=self.gap_pct,
        )
```

becomes:

```python
        # Build-tier / challenger sizing finally binds: scale risk by the
        # analyst chain's size_pct relative to the 2% GRADUAL_BUILD baseline.
        # Clamped so a bad size_pct can never 10x risk or zero it silently.
        size_pct = getattr(recommendation, "size_pct", 0.0) or 0.0
        if size_pct > 0:
            scale = max(0.25, min(2.0, size_pct / 0.02))
            effective_risk_pct = self.risk_pct * scale
        else:
            effective_risk_pct = self.risk_pct

        shares = size_shares(
            capital=self.capital,
            risk_pct=effective_risk_pct,
            entry=recommendation.entry,
            stop_loss=recommendation.stop_loss,
            gap_pct=self.gap_pct,
        )
```

- [ ] **Step 4: Run the full risk test suite**

Run: `.venv/bin/python -m pytest tests/equities/ -q -k "kernel or sizing or risk"`
Expected: all PASS — if an existing test asserts exact share counts for a swing rec with `size_pct != 0.02`, update that test's expectation to the scaled value (it was asserting the old no-op behavior).

- [ ] **Step 5: Commit + push**

```bash
git add equities/risk/kernel.py tests/
git commit -m "feat(kernel): size_pct binds in swing sizing — challenger verdicts now move dollars

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 4: Minimum reward:risk gate

Schema only enforces `stop < entry < target` (`schema.py:71-78`) — a $5-risk/$0.50-reward trade passes today. PTJ asymmetry arithmetic: enforce R:R ≥ 2 in the kernel.

**Files:**
- Modify: `core/config.py` (add field after `equity_risk_pct`, line ~40): `equity_min_rr: float = 2.0`
- Modify: `equities/risk/kernel.py` (swing branch, immediately after the `missing_stop_or_entry` check, line ~177); `RiskKernel.__init__` gains `min_rr: float = 2.0` param stored as `self.min_rr`
- Modify: `runner_equities.py` — the `RiskKernel(...)` construction (grep `RiskKernel(` — single call site) gains `min_rr=settings.equity_min_rr`
- Test: same kernel test file as Task 3

**Interfaces:**
- Produces: rejection reason string `f"rr_{rr:.2f}_below_min_{self.min_rr:.1f}"`. `min_rr=0` disables the gate.

- [ ] **Step 1: Write the failing test**

```python
def test_min_rr_gate_rejects_poor_asymmetry(kernel_and_rec_factory):
    kernel, make_rec = kernel_and_rec_factory  # construct kernel with min_rr=2.0
    # risk $5, reward $2.50 -> rr 0.5 -> reject
    bad = make_rec(entry=100.0, stop_loss=95.0, take_profit=102.5)
    sized = kernel.approve(bad, [], today_realized_loss=0.0, current_equity=100_000)
    assert not sized.approved
    assert "rr_" in (sized.rejection_reason or "")

    # risk $5, reward $12 -> rr 2.4 -> passes the gate
    good = make_rec(entry=100.0, stop_loss=95.0, take_profit=112.0)
    sized = kernel.approve(good, [], today_realized_loss=0.0, current_equity=100_000)
    assert sized.approved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest <kernel test file> -q -k min_rr`
Expected: FAIL — bad trade is approved (no gate exists)

- [ ] **Step 3: Implement**

`core/config.py`, after `equity_risk_pct` (line 40):

```python
    equity_min_rr: float = 2.0  # min (take_profit-entry)/(entry-stop); 0 disables
```

`kernel.py` `__init__`: add `min_rr: float = 2.0` parameter and `self.min_rr = min_rr`.

`kernel.py` swing branch, after the existing:

```python
        if recommendation.stop_loss is None or recommendation.entry is None:
            return SizedRecommendation(recommendation, 0.0, False, "missing_stop_or_entry")
```

insert:

```python
        # --- Minimum reward:risk asymmetry gate ---
        if self.min_rr > 0 and recommendation.take_profit is not None:
            risk = recommendation.entry - recommendation.stop_loss
            reward = recommendation.take_profit - recommendation.entry
            if risk > 0:
                rr = reward / risk
                if rr < self.min_rr:
                    return SizedRecommendation(
                        recommendation, 0.0, False,
                        f"rr_{rr:.2f}_below_min_{self.min_rr:.1f}",
                    )
```

`runner_equities.py`: add `min_rr=settings.equity_min_rr,` to the `RiskKernel(...)` construction.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/ -q -k "kernel or rr"` — all PASS. If existing kernel tests use take_profit values with rr < 2, pass `min_rr=0` in their kernel construction (they test other gates, not this one).

- [ ] **Step 5: Commit + push**

```bash
git add core/config.py equities/risk/kernel.py runner_equities.py tests/
git commit -m "feat(kernel): minimum 2:1 reward:risk gate (EQUITY_MIN_RR)

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 5: Hard-gate do_not_chase / trend_ok

`RelativeStrengthEvidence` already computes structured `trend_ok: bool` and `do_not_chase: bool` (`relative_strength.py:23,26`) but they only reach the LLM as prose. Drop failing candidates before the Haiku prefilter.

**Files:**
- Modify: `runner_equities.py` — RS enrichment loop (line ~813-825) + new helper near `_apply_sizing_verdict` (line ~566)
- Modify: `core/config.py`: `equity_hard_tech_gate: bool = True`
- Test: `tests/equities/test_hard_tech_gate.py` (create)

**Interfaces:**
- Produces: pure helper in `runner_equities.py`: `_passes_tech_gate(evidence) -> tuple[bool, str]` where evidence has `.trend_ok`/`.do_not_chase` attrs (or is None → passes). Testable without the pipeline.

- [ ] **Step 1: Write the failing test**

Create `tests/equities/test_hard_tech_gate.py`:

```python
from types import SimpleNamespace

from runner_equities import _passes_tech_gate


def test_gate_drops_do_not_chase():
    ev = SimpleNamespace(trend_ok=True, do_not_chase=True)
    ok, reason = _passes_tech_gate(ev)
    assert not ok and reason == "do_not_chase"


def test_gate_drops_trend_fail():
    ev = SimpleNamespace(trend_ok=False, do_not_chase=False)
    ok, reason = _passes_tech_gate(ev)
    assert not ok and reason == "trend_fail"


def test_gate_passes_clean_and_missing_evidence():
    ev = SimpleNamespace(trend_ok=True, do_not_chase=False)
    assert _passes_tech_gate(ev) == (True, "")
    assert _passes_tech_gate(None) == (True, "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/equities/test_hard_tech_gate.py -q`
Expected: FAIL — `ImportError: cannot import name '_passes_tech_gate'`

- [ ] **Step 3: Implement**

In `runner_equities.py`, add near `_apply_sizing_verdict` (line ~566):

```python
def _passes_tech_gate(evidence) -> tuple[bool, str]:
    """Hard technical gate: post-spike chases and broken trends never reach the LLM.

    MAX-effect evidence: buying post-spike names is the counterparty's trade.
    Missing evidence passes — the gate only acts on affirmative red flags.
    """
    if evidence is None:
        return True, ""
    if getattr(evidence, "do_not_chase", False):
        return False, "do_not_chase"
    if not getattr(evidence, "trend_ok", True):
        return False, "trend_fail"
    return True, ""
```

Then in the RS enrichment loop (line ~813) — current code:

```python
            enriched_candidates = []
            for candidate in swing_candidates:
                evidence = rs_evidence.get(candidate.instrument.ticker)
                if evidence is None:
                    enriched_candidates.append(candidate)
                    continue
                enriched_candidates.append(
                    replace(
                        candidate,
                        evidence=f"{candidate.evidence} | Technicals: {evidence.evidence}",
                    )
                )
                print(f"  [RS] {candidate.instrument.ticker}: {evidence.evidence}")
            swing_candidates = enriched_candidates
```

becomes:

```python
            enriched_candidates = []
            hard_gate = getattr(settings, "equity_hard_tech_gate", True)
            for candidate in swing_candidates:
                evidence = rs_evidence.get(candidate.instrument.ticker)
                if evidence is None:
                    enriched_candidates.append(candidate)
                    continue
                if hard_gate:
                    ok, gate_reason = _passes_tech_gate(evidence)
                    if not ok:
                        print(
                            f"  [TECH GATE] {candidate.instrument.ticker}: "
                            f"dropped ({gate_reason})"
                        )
                        continue
                enriched_candidates.append(
                    replace(
                        candidate,
                        evidence=f"{candidate.evidence} | Technicals: {evidence.evidence}",
                    )
                )
                print(f"  [RS] {candidate.instrument.ticker}: {evidence.evidence}")
            swing_candidates = enriched_candidates
```

`core/config.py`, after `equity_min_rr`:

```python
    equity_hard_tech_gate: bool = True  # drop do_not_chase/trend-fail pre-LLM
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/test_hard_tech_gate.py -q && .venv/bin/python -c "import runner_equities"`
Expected: PASS + clean import

- [ ] **Step 5: Commit + push**

```bash
git add runner_equities.py core/config.py tests/equities/test_hard_tech_gate.py
git commit -m "feat(screen): hard technical gate — do_not_chase/trend-fail dropped pre-LLM

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 6: Ledger groundwork — high-water mark + horizon persistence

Trailing stops need each position's highest close since entry; the horizon time stop needs the analyst's stated horizon. Both stored at the ledger layer.

**Files:**
- Modify: `equities/ledger_equity.py` — `_ensure_column` call in `__init__` (mirror the existing `_ensure_column` usage — find with `grep -n "_ensure_column" equities/ledger_equity.py`), `mark()` (line ~128), `open_position()` (line ~90)
- Test: `tests/equities/test_ledger_high_water.py` (create)

**Interfaces:**
- Produces: positions rows gain `high_water_price REAL` (backfilled NULL → treated as `entry_price`); `mark()` ratchets it: `high_water_price = MAX(COALESCE(high_water_price, entry_price), new_price)`. `open_position` stores `rec.horizon` inside `analysis_json` under key `"horizon"`. Tasks 7/8 consume `pos["high_water_price"]` and `json.loads(pos["analysis_json"]).get("horizon")`.

- [ ] **Step 1: Write the failing test**

Create `tests/equities/test_ledger_high_water.py`:

```python
import json
from datetime import datetime, timezone

from equities.ledger_equity import EquityLedger
from equities.strategy import Recommendation, Sleeve
from core.assets.instrument import Instrument, CapTier


def _rec(**kw):
    defaults = dict(
        instrument=Instrument("TEST", "Test Co", "NYSE", CapTier.LARGE),
        sleeve=Sleeve.SWING, side="buy", entry=100.0, stop_loss=95.0,
        take_profit=115.0, size_pct=0.02, confidence=0.7,
        catalyst="c", thesis="t", horizon="2-3 weeks",
    )
    defaults.update(kw)
    return Recommendation(**defaults)


def test_mark_ratchets_high_water(tmp_path):
    ledger = EquityLedger(tmp_path / "eq.db")
    pid = ledger.open_position(_rec(), 10.0, 100.0, datetime.now(tz=timezone.utc), mode="paper")
    ledger.mark("TEST", 108.0)
    ledger.mark("TEST", 103.0)   # pullback must NOT lower high water
    pos = {p["id"]: p for p in ledger.open_positions()}[pid]
    assert pos["high_water_price"] == 108.0
    assert pos["mark_price"] == 103.0


def test_horizon_persisted_in_analysis_json(tmp_path):
    ledger = EquityLedger(tmp_path / "eq.db")
    pid = ledger.open_position(_rec(horizon="1-2 weeks"), 10.0, 100.0,
                               datetime.now(tz=timezone.utc), mode="paper")
    pos = {p["id"]: p for p in ledger.open_positions()}[pid]
    assert json.loads(pos["analysis_json"])["horizon"] == "1-2 weeks"
```

(Adjust the `Instrument` import path if it differs — check with `grep -rn "class Instrument" core/ equities/` and copy the constructor form used in existing tests.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/equities/test_ledger_high_water.py -q`
Expected: FAIL — `KeyError: 'high_water_price'` / horizon key missing

- [ ] **Step 3: Implement**

`ledger_equity.py` `__init__` — after the existing `_ensure_column` calls, following the same form:

```python
        self._ensure_column("high_water_price", "REAL")
```

`mark()` — current UPDATE:

```python
        updates = [
            (price, (price - r["entry_price"]) * r["shares"], r["id"])
            for r in rows
        ]
        self._con.executemany(
            "UPDATE positions SET mark_price = ?, unrealized_pnl = ? WHERE id = ?",
            updates,
        )
```

becomes:

```python
        updates = [
            (price, (price - r["entry_price"]) * r["shares"], price, r["id"])
            for r in rows
        ]
        self._con.executemany(
            "UPDATE positions SET mark_price = ?, unrealized_pnl = ?, "
            "high_water_price = MAX(COALESCE(high_water_price, entry_price), ?) "
            "WHERE id = ?",
            updates,
        )
```

`open_position()` — one line change:

```python
        analysis_json = json.dumps(rec.analysis or {}, ensure_ascii=False)
```

becomes:

```python
        analysis_json = json.dumps(
            {**(rec.analysis or {}), "horizon": rec.horizon}, ensure_ascii=False
        )
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/test_ledger_high_water.py tests/equities/ -q -k "ledger or csv or paper"`
Expected: all PASS (the CSV writer selects named `_CSV_HEADERS`; the new column not being listed there is fine — verify no test asserts full column lists).

- [ ] **Step 5: Commit + push**

```bash
git add equities/ledger_equity.py tests/equities/test_ledger_high_water.py
git commit -m "feat(ledger): high-water mark column + horizon persistence for exit engine

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 7: Exit engine v2 — breakeven ratchet, R-trail, horizon time stop

The heart of report item #1. Stateless: effective stop derived every night from `(entry, stop_loss, take_profit, high_water_price)`. `take_profit` stops being an exit — it becomes the trail activator (winners run). The deleted time stop returns horizon-aware (losers can't ride forever).

**Files:**
- Modify: `equities/risk/exits.py` (extend; keep `check_exit` for backward compat)
- Test: `tests/equities/risk/test_exits.py` (append)

**Interfaces:**
- Produces:
  - `_horizon_days(text: str | None, default: int = 21) -> int` — parses "1-2 weeks" → 14, "10 days" → 10, "3 months" → 90; unparseable/None → default.
  - `evaluate_exit(position: dict, current_price: float, today: date, trail_r: float = 1.5, default_horizon_days: int = 21) -> ExitSignal | None` — position dict needs keys `id`, `entry_price`, `stop_loss`, `take_profit`, `high_water_price`, `opened_at`, `analysis_json`. New reasons: `"trailing_stop_hit"`, `"time_stop"`.
- Consumes: Task 6's `high_water_price` + horizon in `analysis_json`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/equities/risk/test_exits.py`:

```python
import json
from datetime import date

from equities.risk.exits import _horizon_days, evaluate_exit


def _pos(**kw):
    base = dict(
        id=1, entry_price=100.0, stop_loss=90.0, take_profit=120.0,
        high_water_price=None, opened_at="2026-07-01T00:00:00+00:00",
        analysis_json=json.dumps({"horizon": "3-4 weeks"}),
    )
    base.update(kw)
    return base


def test_horizon_days_parsing():
    assert _horizon_days("1-2 weeks") == 14
    assert _horizon_days("10 days") == 10
    assert _horizon_days("3 months") == 90
    assert _horizon_days("gibberish") == 21
    assert _horizon_days(None) == 21


def test_hard_stop_still_fires():
    sig = evaluate_exit(_pos(), current_price=89.0, today=date(2026, 7, 5))
    assert sig is not None and sig.reason == "stop_hit"


def test_target_touch_no_longer_exits():
    # price above take_profit: old engine exited; new engine holds (trail active)
    sig = evaluate_exit(_pos(high_water_price=121.0), current_price=121.0,
                        today=date(2026, 7, 5))
    assert sig is None


def test_breakeven_ratchet_after_one_r():
    # R = 10. high water 111 (>= entry + 1R) ratchets stop to entry (100).
    sig = evaluate_exit(_pos(high_water_price=111.0), current_price=99.0,
                        today=date(2026, 7, 5))
    assert sig is not None and sig.reason == "trailing_stop_hit"
    # ...but a price above entry holds
    assert evaluate_exit(_pos(high_water_price=111.0), current_price=101.0,
                         today=date(2026, 7, 5)) is None


def test_r_trail_after_target_activation():
    # R = 10, trail_r = 1.5 -> trail distance 15. HW 130 -> trail stop 115.
    pos = _pos(high_water_price=130.0)
    sig = evaluate_exit(pos, current_price=114.0, today=date(2026, 7, 5))
    assert sig is not None and sig.reason == "trailing_stop_hit"
    assert evaluate_exit(pos, current_price=116.0, today=date(2026, 7, 5)) is None


def test_horizon_time_stop():
    # horizon "3-4 weeks" = 28 days from 2026-07-01 -> fires on day 29+
    assert evaluate_exit(_pos(), current_price=105.0, today=date(2026, 7, 20)) is None
    sig = evaluate_exit(_pos(), current_price=105.0, today=date(2026, 7, 30))
    assert sig is not None and sig.reason == "time_stop"


def test_dca_sleeve_skips_price_exits():
    # CORE: no stop, no target — nothing fires (no time stop for core either)
    pos = _pos(stop_loss=None, take_profit=None,
               analysis_json=json.dumps({}))
    assert evaluate_exit(pos, current_price=1.0, today=date(2027, 7, 5)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/equities/risk/test_exits.py -q`
Expected: FAIL — `ImportError: cannot import name 'evaluate_exit'`

- [ ] **Step 3: Implement**

Append to `equities/risk/exits.py`:

```python
import json
import re
from datetime import date, datetime

_WEEK = 7
_MONTH = 30


def _horizon_days(text: str | None, default: int = 21) -> int:
    """Parse an analyst horizon string ("1-2 weeks", "10 days", "3 months") to days.

    Takes the UPPER bound of a range — the time stop is a backstop, not a target.
    """
    if not text:
        return default
    m = re.search(r"(\d+)\s*(?:-\s*(\d+))?\s*(day|week|month)", text.lower())
    if not m:
        return default
    n = int(m.group(2) or m.group(1))
    unit = m.group(3)
    if unit == "day":
        return n
    if unit == "week":
        return n * _WEEK
    return n * _MONTH


def evaluate_exit(
    position: dict,
    current_price: float,
    today: date,
    trail_r: float = 1.5,
    default_horizon_days: int = 21,
) -> ExitSignal | None:
    """Stateless nightly exit evaluation for swing positions.

    Effective stop = max of:
      - the original hard stop
      - entry (breakeven) once high-water >= entry + 1R
      - high_water - trail_r * R once high-water >= take_profit (trail mode;
        take_profit is an ACTIVATOR, not an exit — winners run)
    Plus a horizon-aware time stop (upper bound of the analyst's horizon).

    CORE positions (no stop) are never exited here.
    """
    entry = position.get("entry_price")
    stop = position.get("stop_loss")
    target = position.get("take_profit")
    pos_id = position["id"]

    if stop is not None and entry is not None and entry > stop:
        r = entry - stop
        hw = position.get("high_water_price") or entry
        effective_stop = stop
        if hw >= entry + r:
            effective_stop = max(effective_stop, entry)  # breakeven ratchet at +1R
        if target is not None and hw >= target:
            effective_stop = max(effective_stop, hw - trail_r * r)  # trail mode
        if current_price <= effective_stop:
            reason = "stop_hit" if effective_stop == stop else "trailing_stop_hit"
            return ExitSignal(position_id=pos_id, reason=reason, exit_price=current_price)

        # Horizon time stop — swing only (requires a stop to identify the sleeve).
        opened_raw = position.get("opened_at") or ""
        try:
            opened = datetime.fromisoformat(opened_raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None
        try:
            horizon = json.loads(position.get("analysis_json") or "{}").get("horizon")
        except (TypeError, ValueError):
            horizon = None
        if (today - opened).days > _horizon_days(horizon, default_horizon_days):
            return ExitSignal(position_id=pos_id, reason="time_stop", exit_price=current_price)

    return None
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/risk/test_exits.py -q`
Expected: all PASS (old `check_exit` tests untouched and still passing)

- [ ] **Step 5: Commit + push**

```bash
git add equities/risk/exits.py tests/equities/risk/test_exits.py
git commit -m "feat(exits): stateless exit engine v2 — breakeven ratchet, R-trail, horizon time stop

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 8: Wire exit engine v2 into the paper tracker

**Files:**
- Modify: `equities/paper.py` (`mark_and_check_exits`, line ~65)
- Modify: `core/config.py`: `equity_trail_r: float = 1.5`
- Modify: `runner_equities.py` — `EquityPaperTracker(...)` construction (line ~691) gains `trail_r=settings.equity_trail_r`
- Test: `tests/equities/test_paper.py` (append)

**Interfaces:**
- Consumes: `evaluate_exit` from Task 7 (replaces `check_exit` in the tracker; `check_exit` stays exported for compat).
- Produces: `EquityPaperTracker.__init__` gains `trail_r: float = 1.5` keyword. `mark_and_check_exits` behavior change: target touches no longer close; trailing/time exits fire. The ledger `mark()` runs BEFORE `evaluate_exit`, and tonight's price is folded into the local high-water so same-night highs count.

- [ ] **Step 1: Write the failing test**

Append to `tests/equities/test_paper.py` (read the file first; reuse its existing fake-price-feed and recommendation helpers — the assertions below are the contract):

```python
def test_winner_trails_instead_of_capping(tmp_path):
    """Price rides through take_profit; tracker holds, then exits on the trail."""
    ledger = EquityLedger(tmp_path / "eq.db")
    prices = FakePrices()  # dict-backed stub with latest_close(); reuse/define per file pattern
    tracker = EquityPaperTracker(ledger, prices, trail_r=1.5)
    rec = _swing_rec(entry=100.0, stop_loss=90.0, take_profit=120.0)
    tracker.open_position(rec, shares=10.0, fill_price=100.0)

    prices.set("TEST", 125.0)          # through target: NO exit (trail activates)
    assert tracker.mark_and_check_exits() == []

    prices.set("TEST", 130.0)          # new high water 130
    assert tracker.mark_and_check_exits() == []

    prices.set("TEST", 114.0)          # 130 - 1.5*10 = 115 trail -> exit
    fired = tracker.mark_and_check_exits()
    assert len(fired) == 1 and fired[0].reason == "trailing_stop_hit"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/equities/test_paper.py -q -k trails`
Expected: FAIL — exit fires at 125.0 with reason `target_hit` (old engine)

- [ ] **Step 3: Implement**

`equities/paper.py`:

```python
from equities.risk.exits import ExitSignal, check_exit, evaluate_exit
```

`__init__` gains `trail_r: float = 1.5` → `self._trail_r = trail_r`.

`mark_and_check_exits` — replace the check block:

```python
            # Update mark price
            self._ledger.mark(ticker, price)

            # Check exit conditions
            signal = check_exit(
                position_id=pos["id"],
                current_price=price,
                stop_loss=pos.get("stop_loss"),
                take_profit=pos.get("take_profit"),
            )
```

with:

```python
            # Update mark price + high-water first so tonight's high counts
            self._ledger.mark(ticker, price)
            hw = max(
                pos.get("high_water_price") or pos.get("entry_price") or price,
                price,
            )

            signal = evaluate_exit(
                {**pos, "high_water_price": hw},
                current_price=price,
                today=now.date(),
                trail_r=self._trail_r,
            )
```

`core/config.py`, after `equity_hard_tech_gate`:

```python
    equity_trail_r: float = 1.5  # trail distance in R multiples once target reached
```

`runner_equities.py` line ~691: add `trail_r=settings.equity_trail_r,` to `EquityPaperTracker(...)`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/test_paper.py tests/equities/risk/test_exits.py -q`
Expected: all PASS. Any old test asserting `target_hit` closes a position must be updated to the new contract (target = activator) — update the assertion, do not weaken the new engine.

- [ ] **Step 5: Commit + push**

```bash
git add equities/paper.py core/config.py runner_equities.py tests/equities/test_paper.py
git commit -m "feat(paper): tracker uses exit engine v2 — winners trail, losers time-stop

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 9: Execute thesis exits (Telegram → actual sell)

`ThesisHealthChecker` verdicts with `action == "exit"` currently only alert (`runner_equities.py:783-784`). Close the position and sell on Alpaca, mirroring the existing exit-execution block at `runner_equities.py:743-760`.

**Files:**
- Modify: `runner_equities.py` — thesis-health stage (line ~776-784) + new helper near `_passes_tech_gate`
- Test: `tests/equities/test_thesis_exit_execution.py` (create)

**Interfaces:**
- Consumes: `ThesisHealth` (has `.position_id`, `.ticker`, `.action`, `.reason`), `EquityLedger.close_position`, `ForwardPaperTracker.record_exit_for_open_trade`, `alpaca_executor.sell`.
- Produces: helper `_execute_thesis_exit(health, pos, equity_ledger, fp_tracker, alpaca_executor, now) -> bool` in `runner_equities.py`, testable with fakes. Exit reason recorded: `"thesis_invalidated"`.

- [ ] **Step 1: Write the failing test**

Create `tests/equities/test_thesis_exit_execution.py`:

```python
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from runner_equities import _execute_thesis_exit


def _health(action="exit"):
    return SimpleNamespace(position_id=7, ticker="TEST", action=action,
                           status="invalidated", reason="thesis broken")


def _pos():
    return {"id": 7, "ticker": "TEST", "shares": 10.0, "entry_price": 100.0,
            "mark_price": 96.0, "sleeve": "swing", "strategy": "equity_analyst",
            "execution_provider": "alpaca_paper"}


def test_exit_action_closes_and_sells():
    ledger, fp, alpaca = MagicMock(), MagicMock(), MagicMock()
    now = datetime.now(tz=timezone.utc)
    executed = _execute_thesis_exit(_health(), _pos(), ledger, fp, alpaca, now)
    assert executed is True
    ledger.close_position.assert_called_once_with(
        position_id=7, exit_price=96.0, exit_reason="thesis_invalidated", closed_at=now,
    )
    alpaca.sell.assert_called_once_with("TEST", 10.0)
    fp.record_exit_for_open_trade.assert_called_once()


def test_hold_action_does_nothing():
    ledger, fp, alpaca = MagicMock(), MagicMock(), MagicMock()
    executed = _execute_thesis_exit(_health(action="hold"), _pos(), ledger, fp, alpaca,
                                    datetime.now(tz=timezone.utc))
    assert executed is False
    ledger.close_position.assert_not_called()


def test_broker_error_never_blocks_ledger_close():
    ledger, fp, alpaca = MagicMock(), MagicMock(), MagicMock()
    alpaca.sell.side_effect = RuntimeError("api down")
    executed = _execute_thesis_exit(_health(), _pos(), ledger, fp, alpaca,
                                    datetime.now(tz=timezone.utc))
    assert executed is True
    ledger.close_position.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/equities/test_thesis_exit_execution.py -q`
Expected: FAIL — `ImportError: cannot import name '_execute_thesis_exit'`

- [ ] **Step 3: Implement**

Add to `runner_equities.py` (near `_passes_tech_gate`):

```python
def _execute_thesis_exit(health, pos, equity_ledger, fp_tracker, alpaca_executor, now) -> bool:
    """Close a position whose thesis the health checker invalidated.

    Ledger close is authoritative and never blocked by broker failures —
    the paper record must reflect the decision even if the sell errors.
    """
    if health.action != "exit":
        return False
    exit_price = float(pos.get("mark_price") or pos.get("entry_price") or 0.0)
    equity_ledger.close_position(
        position_id=pos["id"],
        exit_price=exit_price,
        exit_reason="thesis_invalidated",
        closed_at=now,
    )
    if alpaca_executor is not None and pos.get("execution_provider") == "alpaca_paper":
        try:
            order = alpaca_executor.sell(pos["ticker"], float(pos["shares"]))
            print(f"  ALPACA SELL [{pos['ticker']}] (thesis exit) order_id={order.id} status={order.status}")
        except Exception as exc:
            print(f"  ALPACA SELL FAILED [{pos['ticker']}] (thesis exit): {exc}")
    fp_tracker.record_exit_for_open_trade(
        ticker=pos["ticker"],
        sleeve=pos.get("sleeve"),
        strategy=pos.get("strategy"),
        exit_price=exit_price,
        is_gap_stop=False,
    )
    return True
```

Rewire the thesis-health stage (line ~776) — current:

```python
        with _stage(stats, "thesis_health"):
            open_swing = [p for p in equity_ledger.open_positions() if p.get("sleeve") == "swing"]
            if open_swing and not mark_only:
                health_checker = ThesisHealthChecker()
                for health in health_checker.check_all(open_swing, news):
                    print(f"  [HEALTH] {health.ticker}: {health.status} -> {health.action} | {health.reason}")
                    if health.action == "exit" and alerts is not None and _telegram_allows("exit"):
                        await _send_alert(f"Thesis exit signal: {health.ticker} — {health.reason}")
```

becomes:

```python
        with _stage(stats, "thesis_health"):
            open_swing = [p for p in equity_ledger.open_positions() if p.get("sleeve") == "swing"]
            if open_swing and not mark_only:
                by_id = {p["id"]: p for p in open_swing}
                health_checker = ThesisHealthChecker()
                for health in health_checker.check_all(open_swing, news):
                    print(f"  [HEALTH] {health.ticker}: {health.status} -> {health.action} | {health.reason}")
                    pos = by_id.get(health.position_id)
                    if pos is None:
                        continue
                    executed = _execute_thesis_exit(
                        health, pos, equity_ledger, fp_tracker,
                        alpaca_executor, datetime.now(tz=timezone.utc),
                    )
                    if executed:
                        print(f"  [THESIS EXIT] {health.ticker}: closed — {health.reason}")
                        if alerts is not None and _telegram_allows("exit"):
                            await _send_alert(f"Thesis exit EXECUTED: {health.ticker} — {health.reason}")
```

Note: `ThesisHealth.position_id` comes from `position.get("id", "")` — an int for ledger rows; the `by_id` lookup uses it directly. Verify `alpaca_executor` and `fp_tracker` are in scope at this stage (`fp_tracker` is constructed at line ~647; if `alpaca_executor` is constructed later in `run_pipeline`, hoist its construction above the thesis-health stage keeping its config guards intact).

- [ ] **Step 4: Run tests + import check**

Run: `.venv/bin/python -m pytest tests/equities/test_thesis_exit_execution.py -q && .venv/bin/python -c "import runner_equities"`
Expected: PASS + clean import

- [ ] **Step 5: Commit + push**

```bash
git add runner_equities.py tests/equities/test_thesis_exit_execution.py
git commit -m "feat(runner): thesis-invalidation exits execute — close ledger + Alpaca sell

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 10: Fix the vol-target shadow-channel NameError

`runner_equities.py:1214` references `price_adapter`, which does not exist in scope (the provider is named `prices`, built at line ~677); the `NameError` is swallowed by the surrounding `try` — the vol-target A/B channel has never recorded a data point.

**Files:**
- Modify: `runner_equities.py:1214`
- Test: existing suite (one-line rename inside the runner; the A/B math itself is covered by `tests/equities/test_sizing_ab_report.py` and `tests/equities/risk/test_vol_target.py`)

- [ ] **Step 1: Verify the bug and the correct name**

Run: `grep -n "price_adapter" runner_equities.py` → exactly one hit (1214).
Run: `sed -n '670,700p' runner_equities.py` → confirm the in-scope provider is `prices` (the `_PriceAdapter` built at ~677). Confirm it has a `closes(ticker)` method (`grep -n "def closes" runner_equities.py equities/data/prices.py`); if `_PriceAdapter` lacks one, add a passthrough delegating to the underlying feed.

- [ ] **Step 2: Fix**

```python
                    closes = price_adapter.closes(rec.instrument.ticker)
```

becomes:

```python
                    closes = prices.closes(rec.instrument.ticker)
```

- [ ] **Step 3: Verify**

Run: `.venv/bin/python -c "import runner_equities" && .venv/bin/python -m pytest tests/equities/ -q -k "vol_target or sizing_ab"`
Expected: clean import, PASS. (Live proof lands on the next `sac run`: the sizing A/B section will show non-empty vol-target rows for new entries.)

- [ ] **Step 4: Commit + push**

```bash
git add runner_equities.py
git commit -m "fix(runner): vol-target shadow channel NameError — price_adapter -> prices

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 11: Honest empirical Kelly (capped, floored to current sizing until n≥30)

Make `KELLY_FRACTION` mean something true: `f = min(kelly_fraction, 0.5) × (bp−q)/b` with `p` from the trade's confidence-band empirical win rate and `b` from the trade's own R:R — used **only** when the band has ≥ `equity_kelly_min_trades` (30) closed trades; otherwise current `risk_pct` sizing stands.

**Files:**
- Modify: `equities/risk/sizing.py` (new function)
- Modify: `equities/risk/kernel.py` (`__init__` gains `kelly_fraction: float = 0.0`, `kelly_min_trades: int = 30`, `win_stats_lookup: Any = None`; swing branch applies it after Task 3's scaling)
- Modify: `core/config.py`: `equity_kelly_min_trades: int = 30`
- Modify: `runner_equities.py` — `RiskKernel(...)` construction passes the three kwargs; lookup closure built from attribution:

```python
    def _win_stats_lookup(confidence: float) -> tuple[int, float]:
        from equities.analysis.attribution import _conf_band, confidence_band_stats
        bucket = confidence_band_stats(str(settings.equity_ledger_path)).get(_conf_band(confidence))
        if bucket is None:
            return (0, 0.0)
        return (bucket.n, bucket.win_rate)
```

- Test: `tests/equities/risk/test_empirical_kelly.py` (create) + kernel test file (append)

**Interfaces:**
- Produces in `sizing.py`: `empirical_kelly_risk_pct(win_rate: float, payoff_b: float, kelly_fraction: float, hard_cap: float = 0.5) -> float | None` — the Kelly-derived risk fraction (fraction of capital lost if the stop fills); `None` when measured edge ≤ 0 (caller keeps/reduces base sizing).
- Produces lookup contract: `win_stats_lookup(confidence: float) -> tuple[int, float]` = `(n_closed_in_band, win_rate)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/equities/risk/test_empirical_kelly.py`:

```python
import pytest

from equities.risk.sizing import empirical_kelly_risk_pct


def test_kelly_math():
    # p=0.6, b=2: f* = (2*0.6 - 0.4)/2 = 0.4; fraction 0.5 -> 0.20
    assert empirical_kelly_risk_pct(0.6, 2.0, kelly_fraction=0.5) == pytest.approx(0.20)


def test_negative_edge_returns_none():
    # p=0.3, b=1: bp - q = 0.3 - 0.7 < 0 -> no Kelly bet
    assert empirical_kelly_risk_pct(0.3, 1.0, kelly_fraction=0.5) is None


def test_fraction_hard_capped_at_half():
    # env says 0.85 -> effective fraction 0.5 (over-Kelly is ruin math, not aggression)
    full = empirical_kelly_risk_pct(0.6, 2.0, kelly_fraction=1.0, hard_cap=0.5)
    env = empirical_kelly_risk_pct(0.6, 2.0, kelly_fraction=0.85, hard_cap=0.5)
    assert env == full == pytest.approx(0.20)
```

Append to the kernel test file:

```python
def test_kelly_used_only_with_sufficient_band_history(kernel_factory, make_swing_rec):
    rich = kernel_factory(risk_pct=0.02, kelly_fraction=0.5, kelly_min_trades=30,
                          win_stats_lookup=lambda conf: (40, 0.6), min_rr=0)
    poor = kernel_factory(risk_pct=0.02, kelly_fraction=0.5, kelly_min_trades=30,
                          win_stats_lookup=lambda conf: (5, 0.9), min_rr=0)
    rec = make_swing_rec(entry=100.0, stop_loss=95.0, take_profit=110.0, size_pct=0.02)
    s_rich = rich.approve(rec, [], today_realized_loss=0.0, current_equity=100_000)
    s_poor = poor.approve(rec, [], today_realized_loss=0.0, current_equity=100_000)
    # b = 10/5 = 2, p = 0.6 -> kelly risk = 0.5*0.4 = 0.20, clamped to 2x base = 0.04
    # poor history -> base path risk 0.02. Rich sizes exactly 2x poor.
    assert s_rich.shares == pytest.approx(2.0 * s_poor.shares, rel=1e-6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/equities/risk/test_empirical_kelly.py -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement**

`equities/risk/sizing.py` — append:

```python
def empirical_kelly_risk_pct(
    win_rate: float,
    payoff_b: float,
    kelly_fraction: float,
    hard_cap: float = 0.5,
) -> float | None:
    """Fractional-Kelly risk (fraction of capital at the stop) from MEASURED stats.

    f* = (b*p - q) / b. Returns None when the measured edge is non-positive —
    Kelly of a negative edge is a short position in your own strategy.
    kelly_fraction is hard-capped: growth is zero at 2x Kelly and estimation
    error makes intended-full-Kelly an overbet, so >hard_cap is never honored.
    """
    if payoff_b <= 0 or not (0.0 <= win_rate <= 1.0):
        return None
    q = 1.0 - win_rate
    f_star = (payoff_b * win_rate - q) / payoff_b
    if f_star <= 0:
        return None
    return min(kelly_fraction, hard_cap) * f_star
```

`kernel.py` — `__init__` additions (stored as attributes):

```python
        kelly_fraction: float = 0.0,          # 0 disables the Kelly path entirely
        kelly_min_trades: int = 30,
        win_stats_lookup: Any = None,         # Callable[[float], tuple[int, float]]
```

Import: `from equities.risk.sizing import size_shares, empirical_kelly_risk_pct, _DEFAULT_GAP_PCT`.

Swing branch — after Task 3's `effective_risk_pct` computation, before `size_shares`:

```python
        # Empirical Kelly: replaces flat risk only when this confidence band
        # has enough closed trades to estimate p honestly (>= kelly_min_trades).
        if self.kelly_fraction > 0 and self._win_stats_lookup is not None:
            try:
                n, win_rate = self._win_stats_lookup(recommendation.confidence)
            except Exception:
                n, win_rate = 0, 0.0
            if n >= self.kelly_min_trades and recommendation.take_profit is not None:
                b = (recommendation.take_profit - recommendation.entry) / (
                    recommendation.entry - recommendation.stop_loss
                )
                kelly = empirical_kelly_risk_pct(win_rate, b, self.kelly_fraction)
                if kelly is not None:
                    effective_risk_pct = min(kelly, 2.0 * self.risk_pct)
                else:
                    # measured edge <= 0 in this band: floor to NIBBLE-scale risk
                    effective_risk_pct = min(effective_risk_pct, 0.5 * self.risk_pct)
```

`core/config.py`, after `equity_trail_r`:

```python
    equity_kelly_min_trades: int = 30  # closed trades per band before Kelly sizing
```

`runner_equities.py`: extend `RiskKernel(...)` construction with `kelly_fraction=settings.kelly_fraction, kelly_min_trades=settings.equity_kelly_min_trades, win_stats_lookup=_win_stats_lookup` (closure from the Files section above, defined just before the construction).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/risk/ -q && .venv/bin/python -m pytest tests/equities/ -q -k kernel`
Expected: all PASS.

- [ ] **Step 5: Commit + push**

```bash
git add equities/risk/sizing.py equities/risk/kernel.py core/config.py runner_equities.py tests/
git commit -m "feat(sizing): honest empirical Kelly — band win rates, hard-capped fraction, n>=30 gate

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 12: Calibration escalation gate in preflight

Prevent the exact thing that just happened: risk knobs escalated at n=10 with inverted calibration. `sac doctor` / preflight fails when `EQUITY_RISK_PCT` exceeds baseline while the ledger shows inversion.

**Files:**
- Create: `equities/eval/calibration.py` (add `equities/eval/__init__.py` if the package doesn't exist — check `ls equities/eval/ 2>/dev/null`)
- Modify: `scripts/preflight.py` — `run_preflight(settings)` (line ~80) adds the check via the existing `result.add(...)` failure pattern
- Test: `tests/equities/eval/test_calibration.py` (create; add `tests/equities/eval/__init__.py` if missing)

**Interfaces:**
- Produces: `calibration_inverted(db_path, min_n: int = 3) -> bool` — True when the top band (`0.75-1.00`) has `n >= min_n` AND a win rate below any lower band that also has `n >= min_n`. And `brier_by_band(db_path) -> dict[str, float]` (mean `(confidence − outcome)²` per band, outcome = 1 if pnl > 0).
- Preflight rule: `settings.equity_risk_pct > 0.005` AND `calibration_inverted(settings.equity_ledger_path)` → failure message. Missing/empty ledger never blocks.

- [ ] **Step 1: Write the failing tests**

Create `tests/equities/eval/test_calibration.py`:

```python
import sqlite3

from equities.eval.calibration import brier_by_band, calibration_inverted


def _seed(path, rows):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE positions (confidence REAL, strategy TEXT, sector TEXT, "
        "exit_reason TEXT, realized_pnl REAL, status TEXT)"
    )
    con.executemany("INSERT INTO positions VALUES (?,?,?,?,?,'closed')", rows)
    con.commit(); con.close()


def test_inversion_detected(tmp_path):
    db = str(tmp_path / "eq.db")
    _seed(db, [
        (0.85, "s", "", "time_stop", -5.0), (0.80, "s", "", "time_stop", -4.0),
        (0.90, "s", "", "stop_hit", -6.0),  # high band 0/3
        (0.50, "s", "", "target_hit", 2.0), (0.55, "s", "", "target_hit", 1.5),
        (0.52, "s", "", "target_hit", 1.0),  # low band 3/3
    ])
    assert calibration_inverted(db) is True
    briers = brier_by_band(db)
    assert briers["0.75-1.00"] > briers["0.00-0.60"]


def test_no_inversion_with_healthy_book(tmp_path):
    db = str(tmp_path / "eq.db")
    _seed(db, [
        (0.85, "s", "", "target_hit", 5.0), (0.80, "s", "", "target_hit", 4.0),
        (0.90, "s", "", "target_hit", 6.0),
        (0.50, "s", "", "stop_hit", -2.0), (0.55, "s", "", "stop_hit", -1.5),
        (0.52, "s", "", "target_hit", 1.0),
    ])
    assert calibration_inverted(db) is False


def test_small_sample_never_inverted(tmp_path):
    db = str(tmp_path / "eq.db")
    _seed(db, [(0.85, "s", "", "time_stop", -5.0)])
    assert calibration_inverted(db) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/equities/eval/test_calibration.py -q`
Expected: FAIL — `ModuleNotFoundError: equities.eval.calibration`

- [ ] **Step 3: Implement**

Create `equities/eval/calibration.py`:

```python
"""Calibration diagnostics from the equity ledger.

Answers one question before any risk escalation: does stated confidence
predict outcomes, or is it inverted? Read-only over the ledger DB.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from equities.analysis.attribution import _conf_band

_HIGH_BAND = "0.75-1.00"


def _closed(db_path: str | Path) -> list[tuple[float, float]]:
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT confidence, realized_pnl FROM positions "
            "WHERE status = 'closed' AND realized_pnl IS NOT NULL "
            "AND confidence IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
    return [(float(c), float(p)) for c, p in rows]


def brier_by_band(db_path: str | Path = "data/equity.db") -> dict[str, float]:
    """Mean (confidence - outcome)^2 per band; outcome = 1 if the trade won."""
    groups: dict[str, list[float]] = {}
    for conf, pnl in _closed(db_path):
        outcome = 1.0 if pnl > 0 else 0.0
        groups.setdefault(_conf_band(conf), []).append((conf - outcome) ** 2)
    return {band: sum(v) / len(v) for band, v in groups.items() if v}


def calibration_inverted(db_path: str | Path = "data/equity.db", min_n: int = 3) -> bool:
    """True when the top confidence band underperforms a lower band, both with n >= min_n."""
    bands: dict[str, list[float]] = {}
    for conf, pnl in _closed(db_path):
        bands.setdefault(_conf_band(conf), []).append(pnl)
    high = bands.get(_HIGH_BAND)
    if high is None or len(high) < min_n:
        return False
    high_wr = sum(1 for p in high if p > 0) / len(high)
    for band, pnls in bands.items():
        if band == _HIGH_BAND or len(pnls) < min_n:
            continue
        low_wr = sum(1 for p in pnls if p > 0) / len(pnls)
        if high_wr < low_wr:
            return True
    return False
```

`scripts/preflight.py` — inside `run_preflight(settings)`:

```python
    # Risk escalation requires calibration: refuse elevated per-trade risk
    # while the ledger shows inverted confidence (the n=10 lesson).
    if settings.equity_risk_pct > 0.005:
        try:
            from equities.eval.calibration import calibration_inverted

            if calibration_inverted(settings.equity_ledger_path):
                result.add(
                    "equity_risk_pct escalated while confidence calibration is "
                    "inverted — run `sac attribution`, fix calibration, then escalate"
                )
        except Exception:
            pass  # missing/empty ledger never blocks preflight
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/eval/test_calibration.py -q && set -a; source .env; set +a; .venv/bin/sac doctor; echo "exit=$?"`
Expected: tests PASS. `sac doctor` on the live ledger **should FAIL** right now (risk is escalated to 0.025 and the live book is inverted) — that failure is the feature working. Surface this to the user; do not "fix" it by weakening the check.

- [ ] **Step 5: Commit + push**

```bash
git add equities/eval/ scripts/preflight.py tests/equities/eval/
git commit -m "feat(eval): calibration inversion gate — preflight blocks risk escalation on inverted book

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 13: Activist 13D detection

Strongest still-alive event edge implementable long-only (~7–8% abnormal around filing, no reversal — Brav et al. 2008). SC 13D/13D/A filings appear under the *subject company's* EDGAR feed, so the existing per-ticker adapter reaches them.

**Files:**
- Modify: `equities/data/filings.py` — the form filter at line ~79 (`if form not in ("8-K", "10-Q", "10-K")`)
- Modify: `equities/screen/event_screen.py` — `EventType` enum (line ~25) + candidate emission in `scan` (mirror the `MATERIAL_FILING` emission at line ~199, matching the actual `Candidate` constructor fields and the scan's existing freshness-date variable)
- Test: `tests/equities/test_filings.py` and the event-screen test file under `tests/equities/screen/` (append to each; read them first and mirror their fake-data patterns — the assertions below are the contract)

**Interfaces:**
- Produces: `EventType.ACTIVIST_13D = "activist_13d"`; filings adapter passes through `SC 13D` / `SC 13D/A` forms; event screen emits a candidate with `urgency=1.0` for a 13D filed within ~10 sessions (14 calendar days), evidence `f"{form_type} filed {filed_date} — activist stake disclosed"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/equities/test_filings.py` (adapt to its existing fake-EDGAR fixture):

```python
def test_sc13d_forms_pass_the_filter(fake_edgar_factory):
    adapter = fake_edgar_factory(
        forms=["SC 13D", "SC 13D/A", "4"],
        dates=["2026-07-10", "2026-07-11", "2026-07-11"],
        items=["", "", ""],
    )
    filings = adapter.recent("TEST", days=30)
    got = {f.form_type for f in filings}
    assert "SC 13D" in got and "SC 13D/A" in got and "4" not in got
```

Append to the event-screen test file:

```python
def test_13d_emits_activist_candidate(screen_with_fakes):
    screen = screen_with_fakes(filings=[fake_filing(form_type="SC 13D", days_ago=2)])
    candidates = screen.scan([TEST_INSTRUMENT])
    activist = [c for c in candidates if c.event_type == EventType.ACTIVIST_13D]
    assert len(activist) == 1
    assert activist[0].urgency == 1.0
    assert "SC 13D" in activist[0].evidence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/equities/test_filings.py -q -k 13d`
Expected: FAIL — SC 13D filtered out / `EventType` has no `ACTIVIST_13D`

- [ ] **Step 3: Implement**

`filings.py` line ~79:

```python
            if form not in ("8-K", "10-Q", "10-K"):
```

becomes:

```python
            if form not in ("8-K", "10-Q", "10-K", "SC 13D", "SC 13D/A"):
```

`event_screen.py`: add to the enum:

```python
    ACTIVIST_13D = "activist_13d"
```

In `scan`, where filings are iterated for `MATERIAL_FILING` (line ~185-199), add before the 8-K item matching:

```python
                if filing.form_type.startswith("SC 13D"):
                    age_days = (today - filing.filed_date).days
                    if age_days <= 14:  # ~10 trading sessions
                        candidates.append(
                            Candidate(
                                instrument=instrument,
                                event_type=EventType.ACTIVIST_13D,
                                evidence=(
                                    f"{filing.form_type} filed {filing.filed_date.isoformat()}"
                                    " — activist stake disclosed"
                                ),
                                urgency=1.0,
                                days_to_event=None,
                            )
                        )
                    continue
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/equities/test_filings.py tests/equities/screen/ -q`
Expected: all PASS

- [ ] **Step 5: Commit + push**

```bash
git add equities/data/filings.py equities/screen/event_screen.py tests/
git commit -m "feat(screen): activist SC 13D detection — strongest verified live event edge

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 14: Probe-then-pyramid (flag OFF by default)

Confirm-then-size: open at 1/3 risk, add two tranches only while price > entry AND the thesis is intact. With inverted calibration, full-size-at-entry maximizes damage exactly when the analyst is most wrongly sure. Ships dark behind `EQUITY_PYRAMID_ENABLED=false`.

**Files:**
- Modify: `core/config.py`: `equity_pyramid_enabled: bool = False`
- Modify: `equities/ledger_equity.py`: new `update_analysis_field(position_id, key, value)`
- Modify: `runner_equities.py`:
  - entry sizing: when the flag is on, swing orders use `sized.shares / 3` and stamp `"tranche": 1, "planned_shares": <full shares>` into `rec.analysis` before `open_position` (mirror how `signal_class` flows)
  - new stage `scale_in` after `thesis_health` (only when flag on and not `mark_only`)
- Test: `tests/equities/test_pyramid.py` (create)

**Interfaces:**
- Produces: `_pyramid_addon_candidates(open_positions: list[dict]) -> list[dict]` pure helper in `runner_equities.py` (eligible = swing, status "open", `1 <= tranche < 3`, `mark_price > entry_price`); `EquityLedger.update_analysis_field`.

- [ ] **Step 1: Write the failing tests**

Create `tests/equities/test_pyramid.py`:

```python
import json

from runner_equities import _pyramid_addon_candidates


def _pos(tranche=1, mark=105.0, entry=100.0, status="open"):
    return {
        "id": 1, "ticker": "TEST", "sleeve": "swing", "status": status,
        "entry_price": entry, "mark_price": mark,
        "analysis_json": json.dumps({"tranche": tranche, "planned_shares": 30.0}),
    }


def test_eligible_position_selected():
    assert _pyramid_addon_candidates([_pos()]) == [_pos()]


def test_underwater_position_not_added_to():
    assert _pyramid_addon_candidates([_pos(mark=99.0)]) == []


def test_full_tranches_not_added_to():
    assert _pyramid_addon_candidates([_pos(tranche=3)]) == []


def test_update_analysis_field(tmp_path):
    from datetime import datetime, timezone
    from equities.ledger_equity import EquityLedger
    from tests.equities.test_ledger_high_water import _rec

    ledger = EquityLedger(tmp_path / "eq.db")
    pid = ledger.open_position(_rec(), 10.0, 100.0, datetime.now(tz=timezone.utc), mode="paper")
    ledger.update_analysis_field(pid, "tranche", 2)
    pos = {p["id"]: p for p in ledger.open_positions()}[pid]
    assert json.loads(pos["analysis_json"])["tranche"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/equities/test_pyramid.py -q`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement**

`ledger_equity.py`:

```python
    def update_analysis_field(self, position_id: int, key: str, value) -> None:
        row = self._con.execute(
            "SELECT analysis_json FROM positions WHERE id = ?", (position_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Position {position_id} not found")
        data = json.loads(row["analysis_json"] or "{}")
        data[key] = value
        self._con.execute(
            "UPDATE positions SET analysis_json = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), position_id),
        )
        self._con.commit()
        self._rewrite_csv()
```

`runner_equities.py` helper:

```python
def _pyramid_addon_candidates(open_positions: list[dict]) -> list[dict]:
    """Open swing positions eligible for a confirm-then-size add-on tranche."""
    out = []
    for pos in open_positions:
        if pos.get("sleeve") != "swing" or pos.get("status") != "open":
            continue
        try:
            analysis = json.loads(pos.get("analysis_json") or "{}")
        except ValueError:
            continue
        tranche = int(analysis.get("tranche") or 0)
        if tranche < 1 or tranche >= 3:
            continue  # not a pyramid position, or already full
        mark = pos.get("mark_price")
        entry = pos.get("entry_price")
        if mark is None or entry is None or mark <= entry:
            continue  # only add to winners — that is the whole point
        out.append(pos)
    return out
```

Entry-side change (inside the swing order-placement block, after `sized = kernel.approve(...)` succeeds), when `settings.equity_pyramid_enabled`:

```python
                probe_shares = sized.shares
                if settings.equity_pyramid_enabled:
                    probe_shares = sized.shares / 3.0
                    rec = replace(rec, analysis={
                        **(rec.analysis or {}),
                        "tranche": 1,
                        "planned_shares": sized.shares,
                    })
```

(and use `probe_shares` wherever `sized.shares` fed the order/ledger below — trace each use in that block.)

`scale_in` stage (after the thesis_health stage):

```python
        if settings.equity_pyramid_enabled and not mark_only:
            with _stage(stats, "scale_in"):
                for pos in _pyramid_addon_candidates(equity_ledger.open_positions()):
                    analysis = json.loads(pos["analysis_json"])
                    add_shares = float(analysis["planned_shares"]) / 3.0
                    if alpaca_executor is not None and pos.get("execution_provider") == "alpaca_paper":
                        try:
                            order = alpaca_executor.buy(pos["ticker"], add_shares)
                            print(f"  [SCALE IN] {pos['ticker']} tranche {analysis['tranche'] + 1}: +{add_shares:.4f} sh order={order.id}")
                        except Exception as exc:
                            print(f"  [SCALE IN FAILED] {pos['ticker']}: {exc}")
                            continue
                    equity_ledger.update_analysis_field(pos["id"], "tranche", int(analysis["tranche"]) + 1)
```

Check `alpaca_executor`'s buy method name/signature first (`grep -n "def buy\|def submit" equities/execution/alpaca.py`) and match it. Ledger `shares` stays the probe size in v1 — add-ons live at the broker and reconcile handles the mismatch; mark this with `# ponytail: ledger holds probe shares only; add-on share tracking when reconcile round-trips` after confirming reconcile behavior (`grep -n "reconcile" equities/execution/*.py`).

`core/config.py`, after `equity_kelly_min_trades`:

```python
    equity_pyramid_enabled: bool = False  # probe 1/3, add on confirmation (dark ship)
```

- [ ] **Step 4: Run tests + full suite**

Run: `.venv/bin/python -m pytest tests/equities/test_pyramid.py -q && .venv/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: pyramid tests PASS; full suite green.

- [ ] **Step 5: Commit + push**

```bash
git add core/config.py runner_equities.py equities/ledger_equity.py tests/equities/test_pyramid.py
git commit -m "feat(runner): probe-then-pyramid scale-in behind EQUITY_PYRAMID_ENABLED (default off)

Claude-Session: https://claude.ai/code/session_01YbbMZsvbxaEZS5ogszDtn7"
git push
```

---

### Task 15: Full verification + PR

- [ ] **Step 1: Full test suite**

Run: `.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5`
Expected: all PASS, no skips introduced by this work.

- [ ] **Step 2: Live smoke — dry run**

Run: `set -a; source .env; set +a; .venv/bin/python runner_equities.py --dry-run --no-analyse 2>&1 | tail -30`
Expected: pipeline reaches the run summary with `exit_reason=complete`; `[TECH GATE]` lines may appear; no tracebacks.

- [ ] **Step 3: Confirm the escalation gate fires on the live config**

Run: `set -a; source .env; set +a; .venv/bin/sac doctor; echo "exit=$?"`
Expected: **PREFLIGHT FAILED** with the calibration-inversion message (risk is escalated at 0.025 and the book is inverted). Report this to the user as the intended outcome — the user decides whether to lower `EQUITY_RISK_PCT` back to baseline or consciously override.

- [ ] **Step 4: Open PR**

```bash
gh pr create --title "feat: evidence-based risk engine — exits, calibration-gated sizing, honest Kelly, 13D" --body "Implements profit-research-report.md §5 items 1-7,9,10 (universe rebuild excluded — separate plan).

- Exit engine v2: breakeven ratchet at +1R, 1.5R trail once target reached (target = activator, winners run), horizon-aware time stop restored, thesis exits EXECUTE (ledger close + Alpaca sell)
- Calibration-gated sizing: bands with negative realized PnL capped at NIBBLE (EQUITY_CALIBRATION_SIZING)
- size_pct finally binds in swing sizing; challenger 'half' now moves dollars
- Honest Kelly: empirical band win rates, fraction hard-capped 0.5, active only at n>=30/band
- Hard gates: min 2:1 R:R (EQUITY_MIN_RR), do_not_chase/trend-fail dropped pre-LLM
- fix: vol-target shadow channel NameError (price_adapter -> prices)
- Preflight refuses risk escalation while calibration is inverted
- SC 13D activist detection (EventType.ACTIVIST_13D)
- Probe-then-pyramid behind EQUITY_PYRAMID_ENABLED (default off)

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Self-Review (completed at plan time)

- **Spec coverage:** report §5 items — 1 (Tasks 6-9), 2 (Tasks 1-2), 3 (Task 11), 4 (Task 3), 5 (Tasks 4-5), 6 (Task 10), 7 (Task 13), 9 (Task 12), 10 (Task 14). Item 8 (universe rebuild) deliberately excluded → separate plan. ✔
- **Type consistency:** `calibration_size_cap`/`confidence_band_stats` names match across Tasks 1, 2, 11, 12; `evaluate_exit` position-dict keys match Task 6's ledger columns; `ExitSignal.reason` values (`stop_hit`, `trailing_stop_hit`, `time_stop`, `thesis_invalidated`) consistent across Tasks 7-9. ✔
- **Known unknowns flagged inline** (each with its exact discovery command, not placeholders): kernel test file location (Task 3), `Instrument` import path (Task 6), fixture names in `test_paper.py`/`test_filings.py` (Tasks 8, 13), `alpaca_executor.buy` signature + reconcile behavior (Task 14), `alpaca_executor` scope hoisting (Task 9).
