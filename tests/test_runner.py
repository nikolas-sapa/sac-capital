"""Tests for runner.py — end-to-end paper-trading runner (Task 12).

All tests are offline (no network). The Ledger uses tmp_path so each test
gets an isolated sqlite db.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import load_config
from core.execution.paper import PaperExecutor
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_market(best_ask: float = 0.5) -> Market:
    outcome = Outcome(
        token_id="tok-001",
        label="Yes",
        best_bid=best_ask - 0.01,
        best_ask=best_ask,
    )
    return Market(
        condition_id="cond-001",
        question="Will it happen?",
        outcomes=[outcome],
        end_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
        closed=False,
    )


def _make_settings(bankroll_usd=1000.0, kelly_fraction=0.5, max_position_pct=0.02):
    """Return a Settings-like object with the required attrs (no .env needed)."""
    s = load_config(env_file=None)
    s = s.model_copy(update={
        "bankroll_usd": bankroll_usd,
        "kelly_fraction": kelly_fraction,
        "max_position_pct": max_position_pct,
    })
    return s


# ---------------------------------------------------------------------------
# Test A — one signal → one fill, ledger has 1 open position
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_produces_one_fill(tmp_path):
    from runner import run_once
    from strategies.dummy import DummyStrategy

    market = _make_market(best_ask=0.5)
    settings = _make_settings(bankroll_usd=1000.0, kelly_fraction=0.5, max_position_pct=0.02)
    ledger = Ledger(tmp_path / "l.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)

    fills = await run_once([market], [DummyStrategy()], executor, settings)

    assert len(fills) == 1
    assert len(ledger.open_positions()) == 1


# ---------------------------------------------------------------------------
# Test B — MAX_POSITION_PCT cap is enforced
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_caps_at_max_position_pct(tmp_path):
    """With fair_prob=0.95, price=0.5, full-kelly is huge — cap at max_position_pct."""
    from runner import run_once
    from strategies.dummy import DummyStrategy

    # DummyStrategy hard-codes fair_prob=0.65; we need something higher to bust
    # the cap. We build a minimal custom strategy inline.
    class HighEdgeStrategy:
        name = "high_edge"

        def scan(self, markets):
            if not markets:
                return []
            m = markets[0]
            o = m.outcomes[0]
            return [Signal(
                market=m,
                token_id=o.token_id,
                fair_prob=0.95,
                price=0.5,
                confidence=1.0,
                reason="high edge test",
            )]

    bankroll = 1000.0
    max_pct = 0.02
    cap = bankroll * max_pct  # 20.0

    settings = _make_settings(bankroll_usd=bankroll, kelly_fraction=0.5, max_position_pct=max_pct)
    ledger = Ledger(tmp_path / "l.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)

    fills = await run_once([_make_market()], [HighEdgeStrategy()], executor, settings)

    assert len(fills) == 1
    assert abs(fills[0].stake - cap) < 1e-9


# ---------------------------------------------------------------------------
# Test C — skip-don't-force: no edge → zero fills
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_skips_zero_edge(tmp_path):
    """fair_prob == price → kelly = 0 → no fill."""
    from runner import run_once

    class NoEdgeStrategy:
        name = "no_edge"

        def scan(self, markets):
            if not markets:
                return []
            m = markets[0]
            o = m.outcomes[0]
            price = o.best_ask  # 0.5
            return [Signal(
                market=m,
                token_id=o.token_id,
                fair_prob=price,   # fair_prob == price → zero kelly
                price=price,
                confidence=1.0,
                reason="no-edge test",
            )]

    settings = _make_settings()
    ledger = Ledger(tmp_path / "l.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)

    fills = await run_once([_make_market()], [NoEdgeStrategy()], executor, settings)

    assert fills == []
    assert ledger.open_positions() == []


# ---------------------------------------------------------------------------
# Test D — alerts.send is awaited once per fill
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_sends_alert_per_fill(tmp_path):
    """alerts.send should be awaited exactly once for each fill produced."""
    from runner import run_once
    from strategies.dummy import DummyStrategy

    settings = _make_settings()
    ledger = Ledger(tmp_path / "l.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)

    # Build a mock alerts object whose format_fill returns a string and
    # whose send is an AsyncMock so we can assert it was awaited.
    alerts = MagicMock()
    alerts.format_fill = MagicMock(return_value="[PAPER FILL] test")
    alerts.send = AsyncMock()

    fills = await run_once([_make_market()], [DummyStrategy()], executor, settings, alerts=alerts)

    assert len(fills) == 1
    alerts.send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test E — strategy name is attributed to ledger row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_attributes_strategy_name(tmp_path):
    """After run_once with DummyStrategy, the ledger row's strategy == 'dummy'."""
    from runner import run_once
    from strategies.dummy import DummyStrategy

    settings = _make_settings()
    ledger = Ledger(tmp_path / "l.db")
    executor = PaperExecutor(ledger, slippage=0.0, fee_rate=0.0)

    await run_once([_make_market()], [DummyStrategy()], executor, settings)

    positions = ledger.open_positions()
    assert len(positions) == 1
    assert positions[0]["strategy"] == "dummy"
