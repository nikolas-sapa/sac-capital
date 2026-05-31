# Weather Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development or executing-plans.
> **Status:** DRAFT — pending grill-me. **Depends on:** Foundation.

**Goal:** Trade Polymarket daily-temperature markets by pulling multi-model forecasts for the EXACT resolution weather station, building a 3-model consensus, and betting 3 adjacent temperature bins when math edge exists.

**Architecture:** Implements `core.Strategy`. The entire documented edge is: (1) correct station coordinates, (2) `bias_correction=true`, (3) ICON+GFS+ECMWF consensus, (4) 18–30h entry window, (5) 3-bin coverage with price filters. Most of the work is data correctness, not modeling.

**Tech Stack:** Foundation core, `httpx` (open-meteo), the documented station coordinate table.

---

### Task 1: Station coordinate registry (TDD) — THE critical file

**Files:**
- Create: `strategies/weather/stations.py`, `tests/weather/test_stations.py`

- [ ] **Step 1: Failing test** — `STATIONS["Tokyo"]` returns Haneda (RJTT) coords ≈ (35.5494, 139.7798), NOT Narita; `STATIONS["Paris"]` returns Le Bourget, NOT CDG; every entry has `lat, lon, station, unit` and `unit` is "F" for US, "C" for Asia/Europe.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement the full table from the playbook (NYC/KLGA, Atlanta/KATL, Miami/KMIA, Chicago/KORD, Dallas/KDAL, Tokyo/RJTT, HongKong/HKO, Singapore/WSSS, Seoul/RKSI, London/EGLC, Paris/LFPB). Add a `# VERIFY against live market rules` warning docstring.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(weather): resolution station coordinate registry`.

> **Manual gate before any trading:** for each city, open the live Polymarket market, read "recorded at the [NAME] Station", confirm the coordinate matches. The #1 documented loss cause was wrong coordinates.

---

### Task 2: Open-Meteo multi-model client (TDD with fixture)

**Files:**
- Create: `strategies/weather/forecast.py`, `tests/weather/test_forecast.py`, `tests/weather/fixtures/open_meteo.json`

- [ ] **Step 1:** Capture a real open-meteo response (with `models=icon_seamless,gfs_seamless,ecmwf_ifs025`, `bias_correction=true`, `hourly=temperature_2m`) as fixture.
- [ ] **Step 2: Failing test** — `parse_forecast(json)` returns daily max per model + `spread` + `agree (spread<=3.0)`. Assert `bias_correction=true` is in the request params built by `build_url`.
- [ ] **Step 3:** Run, fail.
- [ ] **Step 4:** Implement `build_url(station, date)` and `parse_forecast(json)`. `fetch_forecast` does the network call; parsing tested against fixture.
- [ ] **Step 5:** Run, pass.
- [ ] **Step 6:** Commit `feat(weather): multi-model forecast client with bias correction`.

---

### Task 3: Consensus + outlier logic (TDD)

**Files:**
- Create: `strategies/weather/consensus.py`, `tests/weather/test_consensus.py`

- [ ] **Step 1: Failing test** — given three model maxes, `consensus()` returns center = mean of the tightest pair (if within 1°C) else mean of all three, and flags the outlier; returns `None` when spread > 3°C (skip).
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement consensus + outlier per playbook logic.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(weather): model consensus and outlier detection`.

---

### Task 4: Bin mapping + 3-bin portfolio (TDD)

**Files:**
- Create: `strategies/weather/bins.py`, `tests/weather/test_bins.py`

- [ ] **Step 1: Failing test** — `find_bin(market, temp)` maps a temperature to the right market bin; handles the documented "bin gap" (fallback to nearest midpoint). `build_portfolio(consensus, market)` returns center + 2 adjacent bins (upward-skew if outlier above), else center±1.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `find_bin` (with gap fallback) + `build_portfolio`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(weather): bin mapping and 3-bin portfolio`.

---

### Task 5: Price filters (TDD)

**Files:**
- Create: `strategies/weather/filters.py`, `tests/weather/test_filters.py`

- [ ] **Step 1: Failing test** — `passes_filters(bins)`: reject if sum of 3 bin asks > 0.95 (no math edge), reject if any bin < 0.01 (resolved), reject if any bin > 0.45 (overpriced). Accept otherwise.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement `passes_filters`.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(weather): price-edge filters`.

---

### Task 6: Entry-window gate (TDD)

**Files:**
- Create: `strategies/weather/window.py`, `tests/weather/test_window.py`

- [ ] **Step 1: Failing test** — `in_window(end_date, now)` True only when 18h ≤ hours-to-resolution ≤ 30h.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(weather): 18-30h entry window gate`.

---

### Task 7: Strategy assembly (TDD)

**Files:**
- Create: `strategies/weather/strategy.py`, `tests/weather/test_strategy.py`

- [ ] **Step 1: Failing test** — `WeatherStrategy().scan([market])` end-to-end with injected forecast: emits one `Signal` per qualifying bin with `fair_prob` from consensus distribution, `confidence` from model agreement; emits nothing when window/filters/spread fail.
- [ ] **Step 2:** Run, fail.
- [ ] **Step 3:** Implement: window gate → match city via market question → fetch forecast → consensus → bins → filters → emit Signals.
- [ ] **Step 4:** Run, pass.
- [ ] **Step 5:** Commit `feat(weather): weather strategy assembly`.

---

### Task 8: Paper-run + city-bias tracking

- [ ] **Step 1:** Register `--strategy weather` in `runner.py`.
- [ ] **Step 2:** Add a per-city PnL breakdown to the ledger query (documented: Hong Kong / Tokyo systematically lost — need per-city visibility to apply bias corrections later).
- [ ] **Step 3: Manual** — run paper loop across enabled cities; confirm signals → paper fills.
- [ ] **Step 4:** Commit `feat(weather): per-city pnl tracking + runner registration`.

---

## Self-Review Checklist
- [ ] Station coordinates verified against live market rules (manual gate, Task 1).
- [ ] `bias_correction=true` asserted in request (Task 2).
- [ ] Spread>3°C → skip; price filters → skip. Skip-don't-force enforced.
- [ ] Per-city PnL visible for later bias tuning.
