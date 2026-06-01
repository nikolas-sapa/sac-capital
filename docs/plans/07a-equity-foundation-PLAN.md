# Equity Foundation (Plan 07a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared continuous-asset foundation every equity milestone needs — domain types, the `EquityLedger`, the `ContinuousStrategy`/`Recommendation`/`Fund` contracts, and a swappable price feed — without trading anything.

**Architecture:** New `core/assets/` shared continuous-asset domain (parallel to the binary Polymarket `Signal`/`Fill`, never force-fitted) plus a new `equities/` package. Reuses `core.config` and the `core.ledger` sqlite+CSV pattern. Every external dependency (price data) sits behind a Protocol so tests use fakes and the live feed is swappable.

**Tech Stack:** Python 3.12, `uv`, pytest, frozen dataclasses + `typing.Protocol`, sqlite3 stdlib, `yfinance` for the live price feed.

Spec: `docs/plans/07-equities-analyst-SPEC.md`.

---

### Task 1: `CapTier` + `Instrument` domain type

**Files:**
- Create: `core/assets/__init__.py`
- Create: `core/assets/instrument.py`
- Test: `tests/test_assets_instrument.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assets_instrument.py
from core.assets.instrument import Instrument, CapTier


def test_instrument_holds_identity_and_cap_tier():
    inst = Instrument(ticker="ACME", name="Acme Corp", exchange="NASDAQ", cap_tier=CapTier.SMALL)
    assert inst.ticker == "ACME"
    assert inst.cap_tier is CapTier.SMALL


def test_instrument_is_frozen():
    import dataclasses
    inst = Instrument(ticker="ACME", name="Acme Corp", exchange="NASDAQ", cap_tier=CapTier.LARGE)
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        inst.ticker = "OTHER"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_assets_instrument.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.assets'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/assets/__init__.py
```

```python
# core/assets/instrument.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CapTier(Enum):
    LARGE = "large"
    MID = "mid"
    SMALL = "small"


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    exchange: str
    cap_tier: CapTier
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_assets_instrument.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add core/assets/__init__.py core/assets/instrument.py tests/test_assets_instrument.py
git commit -m "feat(equities): Instrument + CapTier domain type"
```

---

### Task 2: `Bar` + `PriceSeries`

**Files:**
- Create: `core/assets/bar.py`
- Test: `tests/test_assets_bar.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assets_bar.py
from datetime import date

from core.assets.bar import Bar, PriceSeries


def test_bar_holds_ohlcv():
    b = Bar(day=date(2026, 1, 2), open=10.0, high=11.0, low=9.5, close=10.5, volume=1000)
    assert b.close == 10.5
    assert b.volume == 1000


def test_priceseries_closes_in_order():
    bars = [
        Bar(day=date(2026, 1, 2), open=10, high=11, low=9, close=10.5, volume=100),
        Bar(day=date(2026, 1, 3), open=10.5, high=12, low=10, close=11.0, volume=120),
    ]
    ps = PriceSeries(ticker="ACME", bars=bars)
    assert ps.closes == [10.5, 11.0]
    assert ps.latest.close == 11.0


def test_priceseries_latest_none_when_empty():
    ps = PriceSeries(ticker="ACME", bars=[])
    assert ps.latest is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_assets_bar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.assets.bar'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/assets/bar.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class PriceSeries:
    ticker: str
    bars: list[Bar]

    @property
    def closes(self) -> list[float]:
        return [b.close for b in self.bars]

    @property
    def latest(self) -> Bar | None:
        return self.bars[-1] if self.bars else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_assets_bar.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add core/assets/bar.py tests/test_assets_bar.py
git commit -m "feat(equities): Bar + PriceSeries OHLCV types"
```

---

### Task 3: `Sleeve` + `Recommendation` + `ContinuousStrategy` protocol

**Files:**
- Create: `equities/__init__.py`
- Create: `equities/strategy.py`
- Test: `tests/test_equity_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_equity_strategy.py
from core.assets.instrument import Instrument, CapTier
from equities.strategy import Recommendation, Sleeve, ContinuousStrategy


def _inst() -> Instrument:
    return Instrument(ticker="ACME", name="Acme", exchange="NASDAQ", cap_tier=CapTier.SMALL)


def test_swing_rec_carries_stops():
    rec = Recommendation(
        instrument=_inst(), sleeve=Sleeve.SWING, side="buy",
        entry=10.0, stop_loss=9.0, take_profit=13.0,
        size_pct=0.03, confidence=0.6, catalyst="earnings beat",
        thesis="under-covered, gapped on beat", horizon="2-10d",
    )
    assert rec.sleeve is Sleeve.SWING
    assert rec.stop_loss == 9.0


def test_core_sleeve_omits_stops():
    rec = Recommendation(
        instrument=_inst(), sleeve=Sleeve.CORE, side="buy",
        entry=200.0, stop_loss=None, take_profit=None,
        size_pct=0.0, confidence=0.5, catalyst="quality screen",
        thesis="accumulate", horizon="months",
    )
    assert rec.stop_loss is None


def test_strategy_protocol_is_runtime_checkable():
    class Dummy:
        name = "dummy"
        def scan(self, universe):
            return []
    assert isinstance(Dummy(), ContinuousStrategy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_equity_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'equities'`

- [ ] **Step 3: Write minimal implementation**

```python
# equities/__init__.py
```

```python
# equities/strategy.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from core.assets.instrument import Instrument


class Sleeve(Enum):
    CORE = "core"    # long-term DCA, no stops
    SWING = "swing"  # catalyst trade, hard stops


@dataclass(frozen=True)
class Recommendation:
    instrument: Instrument
    sleeve: Sleeve
    side: str                 # "buy" (short out of scope for v1)
    entry: float
    stop_loss: float | None   # None for CORE
    take_profit: float | None # None for CORE
    size_pct: float           # fraction of capital to deploy
    confidence: float         # 0-1
    catalyst: str
    thesis: str
    horizon: str


@runtime_checkable
class ContinuousStrategy(Protocol):
    name: str

    def scan(self, universe: list[Instrument]) -> list[Recommendation]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_equity_strategy.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add equities/__init__.py equities/strategy.py tests/test_equity_strategy.py
git commit -m "feat(equities): Sleeve + Recommendation + ContinuousStrategy protocol"
```

---

### Task 4: `Fund` protocol (orchestrator contract)

**Files:**
- Create: `equities/fund.py`
- Test: `tests/test_fund_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fund_protocol.py
from equities.fund import Fund


def test_fund_protocol_is_runtime_checkable():
    class FakeFund:
        name = "equity"
        def positions(self):
            return []
        def pnl(self):
            return 0.0
        def exposure(self):
            return 0.0
        def set_allocation(self, usd):
            self._alloc = usd
    f = FakeFund()
    assert isinstance(f, Fund)
    f.set_allocation(500.0)
    assert f._alloc == 500.0


def test_object_missing_method_is_not_a_fund():
    class NotAFund:
        name = "x"
    assert not isinstance(NotAFund(), Fund)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fund_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'equities.fund'`

- [ ] **Step 3: Write minimal implementation**

```python
# equities/fund.py
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Fund(Protocol):
    """Contract the future cross-venue orchestrator consumes.

    Polymarket strategies and the equity fund both get wrapped in this
    interface so one allocator can manage heterogeneous venues.
    """
    name: str

    def positions(self) -> list[dict[str, Any]]: ...
    def pnl(self) -> float: ...
    def exposure(self) -> float: ...
    def set_allocation(self, usd: float) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fund_protocol.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add equities/fund.py tests/test_fund_protocol.py
git commit -m "feat(equities): Fund protocol — orchestrator contract"
```

---

### Task 5: `EquityLedger` — open positions

**Files:**
- Create: `equities/ledger_equity.py`
- Test: `tests/test_equity_ledger.py`

Schema mirrors the `core.ledger.Ledger` sqlite+CSV pattern but with a continuous-position shape (entry/stop/target/mark/realized).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_equity_ledger.py
from datetime import datetime

from core.assets.instrument import Instrument, CapTier
from equities.strategy import Recommendation, Sleeve
from equities.ledger_equity import EquityLedger


def _rec() -> Recommendation:
    inst = Instrument(ticker="ACME", name="Acme", exchange="NASDAQ", cap_tier=CapTier.SMALL)
    return Recommendation(
        instrument=inst, sleeve=Sleeve.SWING, side="buy",
        entry=10.0, stop_loss=9.0, take_profit=13.0,
        size_pct=0.03, confidence=0.6, catalyst="beat", thesis="t", horizon="2-10d",
    )


def test_open_position_appears_in_open_positions(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=5.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2, 14, 30), mode="paper", strategy="swing_v1")
    open_pos = led.open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["ticker"] == "ACME"
    assert open_pos[0]["shares"] == 5.0
    assert open_pos[0]["status"] == "open"
    assert open_pos[0]["strategy"] == "swing_v1"
    led.close()


def test_csv_mirror_written(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=5.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2), mode="paper", strategy="swing_v1")
    csv_path = (tmp_path / "eq.csv")
    assert csv_path.exists()
    assert "ACME" in csv_path.read_text()
    led.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_equity_ledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'equities.ledger_equity'`

- [ ] **Step 3: Write minimal implementation**

```python
# equities/ledger_equity.py
"""Equity trade ledger: sqlite (source of truth) + CSV mirror.

Continuous-position shape (NOT the binary Polymarket fills schema):
each open_position() is one row; mark() updates the live mark + unrealized
pnl; close_position() sets exit_price/exit_reason/realized_pnl/status.
"""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from equities.strategy import Recommendation

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS positions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT    NOT NULL,
    sleeve         TEXT    NOT NULL,
    side           TEXT    NOT NULL,
    shares         REAL    NOT NULL,
    entry_price    REAL    NOT NULL,
    stop_loss      REAL,
    take_profit    REAL,
    mark_price     REAL,
    unrealized_pnl REAL,
    realized_pnl   REAL,
    status         TEXT    NOT NULL DEFAULT 'open',
    exit_price     REAL,
    exit_reason    TEXT,
    confidence     REAL    NOT NULL,
    thesis         TEXT    NOT NULL,
    mode           TEXT    NOT NULL,
    opened_at      TEXT    NOT NULL,
    closed_at      TEXT,
    strategy       TEXT    NOT NULL DEFAULT ''
)
"""

_CSV_HEADERS = [
    "id", "ticker", "sleeve", "side", "shares", "entry_price",
    "stop_loss", "take_profit", "mark_price", "unrealized_pnl",
    "realized_pnl", "status", "exit_price", "exit_reason",
    "confidence", "thesis", "mode", "opened_at", "closed_at", "strategy",
]


class EquityLedger:
    def __init__(self, path: str | Path) -> None:
        self._db_path = Path(path)
        self._csv_path = self._db_path.with_suffix(".csv")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._db_path))
        self._con.row_factory = sqlite3.Row
        self._con.execute(_CREATE_TABLE)
        self._con.commit()
        self._ensure_csv_header()

    def open_position(self, rec: Recommendation, shares: float, fill_price: float,
                      opened_at: datetime, mode: str, strategy: str = "") -> int:
        row = (
            rec.instrument.ticker, rec.sleeve.value, rec.side, shares, fill_price,
            rec.stop_loss, rec.take_profit, fill_price, 0.0,
            rec.confidence, rec.thesis, mode, opened_at.isoformat(), strategy,
        )
        cur = self._con.execute(
            """
            INSERT INTO positions
                (ticker, sleeve, side, shares, entry_price, stop_loss, take_profit,
                 mark_price, unrealized_pnl, confidence, thesis, mode, opened_at, strategy)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            row,
        )
        self._con.commit()
        self._rewrite_csv()
        return int(cur.lastrowid)

    def open_positions(self) -> list[dict[str, Any]]:
        rows = self._con.execute(
            "SELECT * FROM positions WHERE status = 'open'"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "EquityLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_csv_header(self) -> None:
        if not self._csv_path.exists():
            with open(self._csv_path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=_CSV_HEADERS).writeheader()

    def _rewrite_csv(self) -> None:
        rows = self._con.execute("SELECT * FROM positions ORDER BY id").fetchall()
        with open(self._csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            w.writeheader()
            for row in rows:
                w.writerow(dict(row))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_equity_ledger.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add equities/ledger_equity.py tests/test_equity_ledger.py
git commit -m "feat(equities): EquityLedger — open positions + CSV mirror"
```

---

### Task 6: `EquityLedger` — mark-to-market + close + realized pnl

**Files:**
- Modify: `equities/ledger_equity.py`
- Test: `tests/test_equity_ledger.py` (add cases)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_equity_ledger.py
def test_mark_updates_unrealized(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=5.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2), mode="paper")
    led.mark("ACME", price=12.0)
    pos = led.open_positions()[0]
    assert pos["mark_price"] == 12.0
    assert pos["unrealized_pnl"] == 10.0   # (12-10)*5
    led.close()


def test_close_sets_realized_and_removes_from_open(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    pid = led.open_position(_rec(), shares=5.0, fill_price=10.0,
                            opened_at=datetime(2026, 1, 2), mode="paper")
    led.close_position(pid, exit_price=13.0, exit_reason="target",
                       closed_at=datetime(2026, 1, 5))
    assert led.open_positions() == []
    assert led.realized_pnl() == 15.0      # (13-10)*5
    led.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_equity_ledger.py -v`
Expected: FAIL — `AttributeError: 'EquityLedger' object has no attribute 'mark'`

- [ ] **Step 3: Write minimal implementation**

Add these methods to `EquityLedger` (before `close`):

```python
    def mark(self, ticker: str, price: float) -> int:
        """Update mark + unrealized pnl for all open rows of a ticker."""
        rows = self._con.execute(
            "SELECT id, shares, entry_price FROM positions "
            "WHERE ticker = ? AND status = 'open'",
            (ticker,),
        ).fetchall()
        updates = [
            (price, (price - r["entry_price"]) * r["shares"], r["id"])
            for r in rows
        ]
        self._con.executemany(
            "UPDATE positions SET mark_price = ?, unrealized_pnl = ? WHERE id = ?",
            updates,
        )
        self._con.commit()
        self._rewrite_csv()
        return len(updates)

    def close_position(self, position_id: int, exit_price: float,
                       exit_reason: str, closed_at: datetime) -> None:
        row = self._con.execute(
            "SELECT shares, entry_price FROM positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        realized = (exit_price - row["entry_price"]) * row["shares"]
        self._con.execute(
            "UPDATE positions SET status='closed', exit_price=?, exit_reason=?, "
            "realized_pnl=?, mark_price=?, unrealized_pnl=0.0, closed_at=? WHERE id=?",
            (exit_price, exit_reason, realized, exit_price, closed_at.isoformat(), position_id),
        )
        self._con.commit()
        self._rewrite_csv()

    def realized_pnl(self) -> float:
        result = self._con.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0.0) FROM positions WHERE status = 'closed'"
        ).fetchone()[0]
        return float(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_equity_ledger.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add equities/ledger_equity.py tests/test_equity_ledger.py
git commit -m "feat(equities): EquityLedger mark-to-market + close + realized pnl"
```

---

### Task 7: `PriceFeed` protocol + `YFinancePriceFeed`

**Files:**
- Create: `equities/data/__init__.py`
- Create: `equities/data/prices.py`
- Test: `tests/test_prices.py`

The protocol is tested with a fake (no network). `YFinancePriceFeed` is tested only for its DataFrame→`PriceSeries` mapping via a monkeypatched `yf.Ticker`, so the suite never hits the network.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prices.py
from datetime import date

import pandas as pd

from core.assets.bar import PriceSeries
from equities.data.prices import PriceFeed, YFinancePriceFeed


def test_pricefeed_protocol_runtime_checkable():
    class FakeFeed:
        def history(self, ticker, period="1y", interval="1d"):
            return PriceSeries(ticker=ticker, bars=[])
    assert isinstance(FakeFeed(), PriceFeed)


def test_yfinance_feed_maps_dataframe_to_priceseries(monkeypatch):
    df = pd.DataFrame(
        {
            "Open": [10.0, 10.5],
            "High": [11.0, 12.0],
            "Low": [9.5, 10.0],
            "Close": [10.5, 11.0],
            "Volume": [1000, 1200],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
        def history(self, period, interval):
            return df

    monkeypatch.setattr("equities.data.prices.yf.Ticker", FakeTicker)

    feed = YFinancePriceFeed()
    ps = feed.history("ACME", period="5d", interval="1d")
    assert ps.ticker == "ACME"
    assert ps.closes == [10.5, 11.0]
    assert ps.bars[0].day == date(2026, 1, 2)
    assert ps.bars[1].volume == 1200


def test_yfinance_feed_empty_df_returns_empty_series(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            pass
        def history(self, period, interval):
            return pd.DataFrame()
    monkeypatch.setattr("equities.data.prices.yf.Ticker", FakeTicker)
    ps = YFinancePriceFeed().history("BADTICKER")
    assert ps.bars == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prices.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'equities.data'`

- [ ] **Step 3: Add the dependency**

Run: `uv add yfinance pandas`
Expected: `pyproject.toml` updated, lockfile resolved.

- [ ] **Step 4: Write minimal implementation**

```python
# equities/data/__init__.py
```

```python
# equities/data/prices.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

import yfinance as yf

from core.assets.bar import Bar, PriceSeries


@runtime_checkable
class PriceFeed(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


class YFinancePriceFeed:
    """Daily OHLCV via yfinance. auto_adjust=True (yfinance default) so
    Close is split/dividend adjusted and there is no separate Adj Close."""

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        bars: list[Bar] = []
        for ts, r in df.iterrows():
            bars.append(
                Bar(
                    day=ts.date(),
                    open=float(r["Open"]),
                    high=float(r["High"]),
                    low=float(r["Low"]),
                    close=float(r["Close"]),
                    volume=int(r["Volume"]),
                )
            )
        return PriceSeries(ticker=ticker, bars=bars)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_prices.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add equities/data/__init__.py equities/data/prices.py tests/test_prices.py pyproject.toml uv.lock
git commit -m "feat(equities): PriceFeed protocol + YFinancePriceFeed"
```

---

### Task 8: Equity config settings

**Files:**
- Modify: `core/config.py`
- Test: `tests/test_config.py` (add a case)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_config.py
def test_equity_defaults_present():
    from core.config import load_config
    cfg = load_config(env_file=None)
    assert cfg.equity_ledger_path.endswith(".db")
    assert cfg.equity_risk_pct == 0.02
```

> Grill Q5: fractional shares confirmed on Revolut → tight 2% default (ratchets to 1%), not the earlier 3%.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_equity_defaults_present -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'equity_ledger_path'`

- [ ] **Step 3: Write minimal implementation**

Add to the `Settings` class in `core/config.py` (alongside the existing fields):

```python
    # --- equities (Plan 07) ---
    equity_ledger_path: str = "data/equity.db"
    equity_risk_pct: float = 0.02          # per-swing-trade risk cap (fractional shares → tight; ratchets to 0.01)
    finnhub_api_key: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_equity_defaults_present -v`
Expected: PASS

- [ ] **Step 5: Run the FULL suite (regression gate)**

Run: `uv run pytest -q`
Expected: all prior Polymarket tests + new equity tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/config.py tests/test_config.py
git commit -m "feat(equities): equity config settings"
```

---

## Definition of Done (Foundation)

- [ ] `core/assets/` exports `Instrument`, `CapTier`, `Bar`, `PriceSeries`.
- [ ] `equities/` exports `Recommendation`, `Sleeve`, `ContinuousStrategy`, `Fund`, `EquityLedger`, `PriceFeed`, `YFinancePriceFeed`.
- [ ] `EquityLedger` round-trips open → mark → close with correct realized/unrealized pnl and a CSV mirror.
- [ ] Price feed is behind a Protocol; the suite never hits the network.
- [ ] Full `uv run pytest -q` is green (no Polymarket regressions).
- [ ] No real-money / broker code exists.

## NEXT after Foundation: `07-SPIKE` (grill Q4)
Before 07b, build the throwaway **synthesis spike** — prove Claude's analysis isn't garbage on ~10 hand-picked tickers before building the machine. See `07-PLAN-INDEX.md`.

## NOT in Foundation (later milestones, gated)
Synthesis spike (07-SPIKE), event-screening (07b), analyst engine (07c), guardian-process risk kernel + paper tracker (07d), forward-paper kill-gate (07e), self-improvement harness (07f), cross-venue orchestrator (later). See `07-equities-analyst-SPEC.md`.
