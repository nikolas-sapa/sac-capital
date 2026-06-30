# Politician Disclosure Screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a politician-disclosure (STOCK Act) signal as a new screener that feeds the existing equities analyst funnel, paper-trading only.

**Architecture:** Mirror the two existing patterns exactly — `equities/data/mantle_signal.py` (stdlib-`urllib`, frozen dataclass, never-raises external signal provider) and `equities/screen/event_screen.py` (a screener that scores a universe into `CandidateEvent` objects sorted by urgency). A new `PoliticianDisclosureProvider` fetches recent public disclosures; a new `PoliticianScreen` filters/scores them into existing `CandidateEvent`s (new `EventType.POLITICIAN_DISCLOSURE`) so they flow into the analyst stage with zero downstream changes. Off by default behind a config flag.

**Tech Stack:** Python 3.x, `uv`, stdlib `urllib`/`json`/`dataclasses`, pytest. **No new dependencies.**

## Global Constraints

- **No new paid dependency.** stdlib only (`urllib.request`, `json`, `datetime`). Matches `mantle_signal.py`.
- **Provider never raises.** All errors surface in a `.error` field on the result; partial results are valid. Matches `mantle_signal.py`.
- **Paper-only.** This is research signal generation. Do not touch execution/live paths.
- **Public disclosures only.** No login/CAPTCHA bypass, no anti-bot evasion, no leaked/staff data. Keep `source_url` on every trade. Set a descriptive `User-Agent`.
- **Off by default.** `politician_signal_enabled: bool = False` in config. Runner skips the stage unless explicitly enabled.
- **Keep three dates separate** everywhere: `transaction_date`, `date_filed`, and (derived) `filing_lag_days`.
- **Follow existing conventions:** frozen dataclasses, `Protocol`-based injectable providers, `print(f"  [PROVIDER] source=... error=...")` on failure with `failure_callback`.

### Source decision (read before Task 1)

The STOCK Act House source is canonical but ships transactions as **PDFs** (no stdlib-parseable structured feed) — fighting that is not a lazy first slice. Slice 1 consumes a **pre-parsed free public JSON feed** (house-stock-watcher / senate-stock-watcher S3 buckets, no auth):

- House: `https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json`
- Senate: `https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json`

These are public, unauthenticated, community-maintained mirrors of the official filings. **They can lag or go stale** — the provider records `fetched_at` + `source` so staleness is visible, and the feed URL is config-injected so Task-N-later can swap to direct official fetching without touching the screener. `# ponytail:` comments mark this ceiling in code.

---

### Task 1: PoliticianDisclosureProvider (data layer)

**Files:**
- Create: `equities/data/politician_disclosures.py`
- Test: `equities/data/tests/test_politician_disclosures.py`

**Interfaces:**
- Consumes: nothing (leaf data provider).
- Produces:
  - `@dataclass(frozen=True) PoliticianTrade` with fields: `ticker: str`, `politician: str`, `chamber: str` (`"house"`/`"senate"`), `transaction_type: str` (`"buy"`/`"sell"`/`"exchange"`), `owner: str`, `amount_min: int`, `amount_max: int`, `transaction_date: date | None`, `date_filed: date | None`, `filing_lag_days: int | None`, `source: str`, `source_url: str`.
  - `@dataclass(frozen=True) DisclosureFetch` with: `trades: list[PoliticianTrade]`, `fetched_at: str`, `source: str`, `error: str | None`.
  - `class PoliticianDisclosureProvider` with `__init__(self, *, house_url: str, senate_url: str, timeout: float = 10.0)` and `fetch(self) -> DisclosureFetch`.
  - Module helper `parse_amount_range(raw: str) -> tuple[int, int]` → `(min, max)`; unknown → `(0, 0)`.

- [ ] **Step 1: Write the failing test for amount parsing + trade normalization**

```python
# equities/data/tests/test_politician_disclosures.py
from datetime import date

from equities.data.politician_disclosures import (
    PoliticianDisclosureProvider,
    PoliticianTrade,
    parse_amount_range,
    _normalize_house_record,
)


def test_parse_amount_range_standard_bracket():
    assert parse_amount_range("$50,001 - $100,000") == (50001, 100000)
    assert parse_amount_range("$1,001 - $15,000") == (1001, 15000)
    assert parse_amount_range("garbage") == (0, 0)


def test_normalize_house_record_buy():
    raw = {
        "ticker": "NVDA",
        "representative": "Nancy Pelosi",
        "type": "purchase",
        "owner": "spouse",
        "amount": "$50,001 - $100,000",
        "transaction_date": "2026-06-10",
        "disclosure_date": "2026-06-29",
        "ptr_link": "https://disclosures-clerk.house.gov/x",
    }
    t = _normalize_house_record(raw)
    assert isinstance(t, PoliticianTrade)
    assert t.ticker == "NVDA"
    assert t.transaction_type == "buy"
    assert t.amount_min == 50001 and t.amount_max == 100000
    assert t.transaction_date == date(2026, 6, 10)
    assert t.date_filed == date(2026, 6, 29)
    assert t.filing_lag_days == 19
    assert t.chamber == "house"


def test_normalize_house_record_missing_ticker_returns_none():
    assert _normalize_house_record({"ticker": "--", "type": "purchase"}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run pytest equities/data/tests/test_politician_disclosures.py -v`
Expected: FAIL — `ModuleNotFoundError: equities.data.politician_disclosures`

- [ ] **Step 3: Implement the provider (mirror `mantle_signal.py`)**

```python
# equities/data/politician_disclosures.py
"""Politician STOCK Act disclosure signals — House + Senate public filings.

Source (slice 1): pre-parsed public JSON mirrors of official STOCK Act filings.
  house  : https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json
  senate : https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json
Both fetches are independent; partial results are valid. Never raises — all
errors surface in DisclosureFetch.error.

# ponytail: community JSON mirror, can lag/go stale. fetched_at + source make
# staleness visible; feed URL is injected so we can swap to direct official
# (House Clerk ZIP/PDF, Senate eFD) fetching later without touching the screener.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone

log = logging.getLogger(__name__)

_USER_AGENT = "sapa-fund-research/1.0 (paper-trading; public-disclosure research)"

_BUY_WORDS = frozenset({"purchase", "buy", "p"})
_SELL_WORDS = frozenset({"sale", "sale_full", "sale_partial", "sell", "s"})

_AMOUNT_RE = re.compile(r"\$?([\d,]+)")


@dataclass(frozen=True)
class PoliticianTrade:
    ticker: str
    politician: str
    chamber: str            # "house" | "senate"
    transaction_type: str   # "buy" | "sell" | "exchange"
    owner: str
    amount_min: int
    amount_max: int
    transaction_date: date | None
    date_filed: date | None
    filing_lag_days: int | None
    source: str
    source_url: str


@dataclass(frozen=True)
class DisclosureFetch:
    trades: list[PoliticianTrade]
    fetched_at: str         # ISO-8601 UTC
    source: str
    error: str | None


def parse_amount_range(raw: str) -> tuple[int, int]:
    if not raw:
        return (0, 0)
    nums = [int(m.replace(",", "")) for m in _AMOUNT_RE.findall(raw)]
    if len(nums) >= 2:
        return (nums[0], nums[1])
    if len(nums) == 1:
        return (nums[0], nums[0])
    return (0, 0)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _classify(raw_type: str | None) -> str:
    t = (raw_type or "").strip().lower()
    if t in _BUY_WORDS or "purchase" in t:
        return "buy"
    if t in _SELL_WORDS or "sale" in t or "sell" in t:
        return "sell"
    return "exchange"


def _build_trade(*, ticker, politician, chamber, raw_type, owner,
                 amount, txn_date, filed_date, url) -> PoliticianTrade | None:
    ticker = (ticker or "").strip().upper()
    if not ticker or ticker in {"--", "N/A", "NA", ""}:
        return None
    amount_min, amount_max = parse_amount_range(amount or "")
    txn = _parse_date(txn_date)
    filed = _parse_date(filed_date)
    lag = (filed - txn).days if (txn and filed) else None
    return PoliticianTrade(
        ticker=ticker,
        politician=(politician or "unknown").strip(),
        chamber=chamber,
        transaction_type=_classify(raw_type),
        owner=(owner or "self").strip(),
        amount_min=amount_min,
        amount_max=amount_max,
        transaction_date=txn,
        date_filed=filed,
        filing_lag_days=lag,
        source=f"{chamber}_stock_watcher",
        source_url=(url or "").strip(),
    )


def _normalize_house_record(raw: dict) -> PoliticianTrade | None:
    return _build_trade(
        ticker=raw.get("ticker"),
        politician=raw.get("representative"),
        chamber="house",
        raw_type=raw.get("type"),
        owner=raw.get("owner"),
        amount=raw.get("amount"),
        txn_date=raw.get("transaction_date"),
        filed_date=raw.get("disclosure_date"),
        url=raw.get("ptr_link"),
    )


def _normalize_senate_record(raw: dict) -> PoliticianTrade | None:
    return _build_trade(
        ticker=raw.get("ticker"),
        politician=raw.get("senator"),
        chamber="senate",
        raw_type=raw.get("type"),
        owner=raw.get("owner"),
        amount=raw.get("amount"),
        txn_date=raw.get("transaction_date"),
        filed_date=raw.get("disclosure_date"),
        url=raw.get("ptr_link"),
    )


def _fetch_json(url: str, *, timeout: float) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class PoliticianDisclosureProvider:
    def __init__(self, *, house_url: str, senate_url: str, timeout: float = 10.0) -> None:
        self._house_url = house_url
        self._senate_url = senate_url
        self._timeout = timeout

    def fetch(self) -> DisclosureFetch:
        trades: list[PoliticianTrade] = []
        errors: list[str] = []
        sources: list[str] = []

        for url, normalizer, label in (
            (self._house_url, _normalize_house_record, "house"),
            (self._senate_url, _normalize_senate_record, "senate"),
        ):
            if not url:
                continue
            try:
                rows = _fetch_json(url, timeout=self._timeout)
                for raw in rows:
                    t = normalizer(raw)
                    if t is not None:
                        trades.append(t)
                sources.append(label)
            except (urllib.error.URLError, ValueError, TimeoutError) as exc:
                msg = f"{label}: {exc}"
                print(f"  [PROVIDER] source=politician_{label} error={exc}")
                errors.append(msg)

        return DisclosureFetch(
            trades=trades,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source="+".join(sources) if sources else "none",
            error="; ".join(errors) if errors else None,
        )
```

- [ ] **Step 4: Run normalization/parse tests to verify they pass**

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run pytest equities/data/tests/test_politician_disclosures.py -v`
Expected: PASS (3 tests). The live `fetch()` is not network-tested here — it is exercised via a stubbed `_fetch_json` in Step 5.

- [ ] **Step 5: Add a never-raises test for `fetch()` with a monkeypatched fetcher**

```python
# append to test_politician_disclosures.py
import equities.data.politician_disclosures as mod
from equities.data.politician_disclosures import PoliticianDisclosureProvider


def test_fetch_partial_failure_never_raises(monkeypatch):
    def fake_fetch_json(url, *, timeout):
        if "house" in url:
            return [{
                "ticker": "AAPL", "representative": "Rep A", "type": "purchase",
                "owner": "self", "amount": "$1,001 - $15,000",
                "transaction_date": "2026-06-01", "disclosure_date": "2026-06-20",
                "ptr_link": "http://x",
            }]
        raise ValueError("senate feed down")

    monkeypatch.setattr(mod, "_fetch_json", fake_fetch_json)
    result = PoliticianDisclosureProvider(house_url="http://house", senate_url="http://senate").fetch()
    assert len(result.trades) == 1
    assert result.trades[0].ticker == "AAPL"
    assert result.source == "house"
    assert result.error is not None and "senate" in result.error
```

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run pytest equities/data/tests/test_politician_disclosures.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add equities/data/politician_disclosures.py equities/data/tests/test_politician_disclosures.py
git commit -m "feat(equities): politician STOCK Act disclosure provider (House+Senate, paper research)"
```

---

### Task 2: PoliticianScreen (scoring → CandidateEvent)

**Files:**
- Create: `equities/screen/politician_screen.py`
- Modify: `equities/screen/event_screen.py` — add one enum member `POLITICIAN_DISCLOSURE = "politician_disclosure"` to `EventType`.
- Test: `equities/screen/tests/test_politician_screen.py`

**Interfaces:**
- Consumes: `PoliticianTrade`, `DisclosureFetch`, `PoliticianDisclosureProvider` from Task 1; `Instrument`, `CapTier` from `core.assets.instrument`; `CandidateEvent`, `EventType` from `equities.screen.event_screen`.
- Produces: `class PoliticianScreen` with `__init__(self, provider, *, lookback_days: int = 30, min_amount: int = 15000)` and `scan(self, universe: list[Instrument]) -> list[CandidateEvent]`. Internal `score_ticker(trades: list[PoliticianTrade], today: date) -> tuple[float, str]` returning `(urgency_0_to_1, evidence)`.

**Scoring (slice 1, deterministic, normalized 0–1).** Per ticker, over buys filed within `lookback_days`:
- `recency` = freshest filing: `1 - lag_days/lookback_days` (clamped ≥0).
- `cluster` = `min(distinct_politicians / 3, 1.0)`.
- `repeat` = `min(total_buys / 3, 1.0)`.
- `size` = `min(max(amount_max) / 250_000, 1.0)`.
- `urgency = 0.35*recency + 0.30*cluster + 0.20*repeat + 0.15*size`.
- Hard rejects: no buys; freshest filing older than `lookback_days`; all `amount_max < min_amount`.

`# ponytail: 4-factor score. committee/policy/sector factors (full 8-factor formula) need extra joined data — Phase 2.`

- [ ] **Step 1: Add the enum member**

In `equities/screen/event_screen.py`, inside `class EventType(Enum)`:

```python
    MATERIAL_FILING = "material_filing"
    POLITICIAN_DISCLOSURE = "politician_disclosure"
```

- [ ] **Step 2: Write the failing test**

```python
# equities/screen/tests/test_politician_screen.py
from datetime import date, timedelta

from core.assets.instrument import CapTier, Instrument
from equities.data.politician_disclosures import DisclosureFetch, PoliticianTrade
from equities.screen.event_screen import EventType
from equities.screen.politician_screen import PoliticianScreen


class _StubProvider:
    def __init__(self, trades):
        self._trades = trades

    def fetch(self):
        return DisclosureFetch(trades=self._trades, fetched_at="t", source="house", error=None)


def _trade(ticker, who, days_ago_filed, amount_max=100000, ttype="buy"):
    today = date.today()
    return PoliticianTrade(
        ticker=ticker, politician=who, chamber="house", transaction_type=ttype,
        owner="self", amount_min=1, amount_max=amount_max,
        transaction_date=today - timedelta(days=days_ago_filed + 5),
        date_filed=today - timedelta(days=days_ago_filed),
        filing_lag_days=5, source="house", source_url="http://x",
    )


_AAPL = Instrument(ticker="AAPL", name="Apple", exchange="NASDAQ", cap_tier=CapTier.LARGE)
_TSLA = Instrument(ticker="TSLA", name="Tesla", exchange="NASDAQ", cap_tier=CapTier.LARGE)


def test_cluster_buy_scores_higher_than_single():
    cluster = _StubProvider([_trade("AAPL", "A", 2), _trade("AAPL", "B", 3), _trade("AAPL", "C", 4)])
    single = _StubProvider([_trade("TSLA", "A", 2)])
    c_aapl = PoliticianScreen(cluster).scan([_AAPL])
    c_tsla = PoliticianScreen(single).scan([_TSLA])
    assert c_aapl and c_aapl[0].event_type == EventType.POLITICIAN_DISCLOSURE
    assert c_aapl[0].urgency > c_tsla[0].urgency


def test_sells_and_off_universe_excluded():
    prov = _StubProvider([_trade("AAPL", "A", 2, ttype="sell"), _trade("NVDA", "B", 2)])
    out = PoliticianScreen(prov).scan([_AAPL])  # NVDA not in universe, AAPL only a sell
    assert out == []


def test_stale_filing_rejected():
    prov = _StubProvider([_trade("AAPL", "A", days_ago_filed=99)])
    assert PoliticianScreen(prov, lookback_days=30).scan([_AAPL]) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run pytest equities/screen/tests/test_politician_screen.py -v`
Expected: FAIL — `ModuleNotFoundError: equities.screen.politician_screen`

- [ ] **Step 4: Implement the screener**

```python
# equities/screen/politician_screen.py
"""Politician STOCK Act disclosure screener — paper research funnel.

Scores recent congressional buy disclosures into CandidateEvents that flow
into the existing analyst stage. Discovery is intersected with the scanned
universe in slice 1 (real Instrument objects only).

# ponytail: 4-factor deterministic score (recency/cluster/repeat/size).
# committee/policy/sector-catalyst factors need joined data — Phase 2.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from core.assets.instrument import Instrument
from equities.screen.event_screen import CandidateEvent, EventType


class DisclosureProvider(Protocol):
    def fetch(self): ...  # returns DisclosureFetch


@dataclass(frozen=True)
class _TickerScore:
    urgency: float
    evidence: str


class PoliticianScreen:
    def __init__(self, provider: DisclosureProvider, *, lookback_days: int = 30,
                 min_amount: int = 15000) -> None:
        self._provider = provider
        self._lookback = lookback_days
        self._min_amount = min_amount

    def scan(self, universe: list[Instrument]) -> list[CandidateEvent]:
        by_ticker = {inst.ticker.upper(): inst for inst in universe}
        fetch = self._provider.fetch()
        today = date.today()

        grouped: dict[str, list] = defaultdict(list)
        for t in fetch.trades:
            if t.transaction_type != "buy":
                continue
            if t.ticker not in by_ticker:
                continue
            if t.date_filed is None or (today - t.date_filed).days > self._lookback:
                continue
            grouped[t.ticker].append(t)

        candidates: list[CandidateEvent] = []
        for ticker, trades in grouped.items():
            scored = self._score(trades, today)
            if scored is None:
                continue
            candidates.append(CandidateEvent(
                instrument=by_ticker[ticker],
                event_type=EventType.POLITICIAN_DISCLOSURE,
                evidence=scored.evidence,
                urgency=round(scored.urgency, 4),
                days_to_event=None,
            ))

        candidates.sort(key=lambda c: c.urgency, reverse=True)
        return candidates

    def _score(self, trades: list, today: date) -> _TickerScore | None:
        if not trades:
            return None
        if all(t.amount_max < self._min_amount for t in trades):
            return None

        freshest_lag = min((today - t.date_filed).days for t in trades)
        recency = max(0.0, 1.0 - freshest_lag / self._lookback)
        distinct = len({t.politician for t in trades})
        cluster = min(distinct / 3.0, 1.0)
        repeat = min(len(trades) / 3.0, 1.0)
        size = min(max(t.amount_max for t in trades) / 250_000.0, 1.0)

        urgency = 0.35 * recency + 0.30 * cluster + 0.20 * repeat + 0.15 * size
        names = ", ".join(sorted({t.politician for t in trades})[:3])
        evidence = (
            f"POL buy: {len(trades)} filing(s), {distinct} politician(s) "
            f"[{names}], freshest {freshest_lag}d ago, "
            f"≤${max(t.amount_max for t in trades):,}"
        )
        return _TickerScore(urgency=urgency, evidence=evidence)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run pytest equities/screen/tests/test_politician_screen.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add equities/screen/politician_screen.py equities/screen/event_screen.py equities/screen/tests/test_politician_screen.py
git commit -m "feat(equities): politician disclosure screener with deterministic 4-factor score"
```

---

### Task 3: Config flags + runner wiring (off by default)

**Files:**
- Modify: `core/config.py` — add three fields.
- Modify: `runner_equities.py` — import + a new `_stage("politician_screen")` block after the relative-strength stage, gated on the flag, appending into `swing_candidates`.
- Test: `tests/test_politician_runner_wiring.py`

**Interfaces:**
- Consumes: `PoliticianScreen` (Task 2), `PoliticianDisclosureProvider` (Task 1), config fields below.
- Produces: politician candidates merged into the existing `swing_candidates` list before the analyst stage. No new output format.

- [ ] **Step 1: Add config fields**

In `core/config.py`, in the config dataclass (near the other equity fields around `equity_provider_timeout_seconds`):

```python
    politician_signal_enabled: bool = False
    politician_house_url: str = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
    politician_senate_url: str = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"
```

If `load_config` reads env vars, also wire `POLITICIAN_SIGNAL_ENABLED` (truthy → bool) following the existing env-parsing pattern in that function; otherwise the dataclass default is sufficient.

- [ ] **Step 2: Write the failing wiring test**

```python
# tests/test_politician_runner_wiring.py
from datetime import date, timedelta

from core.assets.instrument import CapTier, Instrument
from equities.data.politician_disclosures import DisclosureFetch, PoliticianTrade
from equities.screen.event_screen import EventType
from equities.screen.politician_screen import PoliticianScreen


class _StubProvider:
    def __init__(self, trades):
        self._trades = trades

    def fetch(self):
        return DisclosureFetch(trades=self._trades, fetched_at="t", source="house", error=None)


def test_politician_screen_emits_candidate_for_universe_ticker():
    today = date.today()
    trade = PoliticianTrade(
        ticker="MSFT", politician="Rep X", chamber="house", transaction_type="buy",
        owner="self", amount_min=50001, amount_max=100000,
        transaction_date=today - timedelta(days=10), date_filed=today - timedelta(days=3),
        filing_lag_days=7, source="house", source_url="http://x",
    )
    universe = [Instrument(ticker="MSFT", name="Microsoft", exchange="NASDAQ", cap_tier=CapTier.LARGE)]
    out = PoliticianScreen(_StubProvider([trade])).scan(universe)
    assert len(out) == 1
    assert out[0].instrument.ticker == "MSFT"
    assert out[0].event_type == EventType.POLITICIAN_DISCLOSURE
    assert 0.0 < out[0].urgency <= 1.0
```

- [ ] **Step 3: Run to verify it passes already (screener is done) — this test guards the contract the runner depends on**

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run pytest tests/test_politician_runner_wiring.py -v`
Expected: PASS (1 test).

- [ ] **Step 4: Wire the runner stage**

In `runner_equities.py`, add to the screen imports (near line 55–63):

```python
from equities.screen.politician_screen import PoliticianScreen
from equities.data.politician_disclosures import PoliticianDisclosureProvider
```

Then, immediately after the `relative_strength_screen` stage closes (after `swing_candidates = enriched_candidates`, ~line 745) and before the `# --- Core screen ---` comment, add:

```python
        # --- Politician disclosure screen (off by default) ---
        if getattr(cfg, "politician_signal_enabled", False):
            with _stage(stats, "politician_screen"):
                pol_provider = PoliticianDisclosureProvider(
                    house_url=cfg.politician_house_url,
                    senate_url=cfg.politician_senate_url,
                    timeout=cfg.equity_provider_timeout_seconds,
                )
                pol_candidates = PoliticianScreen(pol_provider).scan(swing_universe)
                for c in pol_candidates:
                    print(f"  [POL] {c.instrument.ticker}: {c.evidence} (urgency={c.urgency:.2f})")
                swing_candidates = swing_candidates + pol_candidates
```

Use whatever the config variable is named in that scope (`cfg` / `config`) — match the surrounding lines.

- [ ] **Step 5: Verify runner imports and screen-only mode run clean**

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run python -c "import runner_equities"` then `cd /Users/nikolassapalidis/sapa_fund && POLITICIAN_SIGNAL_ENABLED=0 uv run python runner_equities.py --no-analyse 2>&1 | tail -20`
Expected: imports clean; screen-only run completes without the politician stage (flag off). No traceback.

- [ ] **Step 6: Run the full equities test suite to confirm nothing regressed**

Run: `cd /Users/nikolassapalidis/sapa_fund && uv run pytest equities tests -q`
Expected: all pass (existing + 8 new).

- [ ] **Step 7: Commit**

```bash
git add core/config.py runner_equities.py tests/test_politician_runner_wiring.py
git commit -m "feat(equities): wire politician disclosure screen into runner (off by default)"
```

---

## Self-Review

- **Spec coverage:** data sources (provider, House+Senate public JSON, swappable) ✓; legal/compliance (public-only, never-raises, source_url kept, paper-only, off by default) ✓; pipeline fetch→normalize→score→emit ✓; JSON schema → `PoliticianTrade` dataclass fields ✓; scoring formula → 4-factor deterministic (Phase 2 = full 8-factor) ✓; integration point = screener funnel (not the blind standalone CLI) ✓; risks → captured below. **Frontend badge + backtest deferred to Phase 2** (noted, not built — YAGNI for first commit).
- **Placeholder scan:** none — every step has runnable code/commands.
- **Type consistency:** `PoliticianTrade`/`DisclosureFetch`/`PoliticianDisclosureProvider.fetch()`/`PoliticianScreen.scan()` names and fields match across Tasks 1–3 and all tests.

---

## Phase 2 backlog (do NOT build yet)

- **Direct official sourcing** for freshness: House Clerk annual ZIP + PDF PTR parse; Senate eFD; OGE 278e for cabinet/administration. Swap behind the same `fetch()` interface.
- **Off-universe discovery:** emit candidates for politician-bought tickers *not* in the scanned universe (construct `Instrument` w/ cap-tier lookup).
- **Full 8-factor score:** add committee-relevance, policy/administration-relevance, sector/catalyst overlap. Needs a politician→committee map + sector tags.
- **Backtest** (`equities/research/`): entry at first open after `date_filed`, hold 20/60/120 trading days, excess return vs sector ETF. Reuse `research/backtest.py` patterns.
- **Frontend badge** (`frontend/src`): compact `POL Buy · High` chip in the ticker table; expanded row shows politician/office, transaction_date vs date_filed, lag, source_url. Per design-DNA: monochrome accent, no cards, no hype labels.

## Risks & limitations

- **Disclosure lag is the signal's ceiling:** STOCK Act allows up to 30–45 days; the edge is post-disclosure drift, not front-running. `filing_lag_days` is surfaced so stale signals score low.
- **Community feed staleness/accuracy:** slice-1 source is a public mirror, not canonical — validate samples against official filings before trusting live; `source`/`fetched_at` expose drift. Swap to official in Phase 2.
- **Range-only amounts + spouse/owner attribution:** sizes are brackets; `owner` field retained but not yet weighted.
- **ToS/robots:** slice-1 sources are public unauthenticated JSON; set `User-Agent`, no auth/CAPTCHA bypass. Re-check terms before adding any scraped (non-API) source in Phase 2.
- **Not financial advice / not insider data:** public lagged disclosures only, paper-trading research.

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-06-30-politician-disclosure-screen.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — execute Tasks 1→3 in this session with checkpoints.

Which approach?
