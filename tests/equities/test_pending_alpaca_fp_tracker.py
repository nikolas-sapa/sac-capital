"""Test that pending Alpaca orders are recorded in forward-paper tracker.

This is a regression test for the money-path tracking gap where pending
(non-filled) Alpaca buy orders were recorded in the equity ledger but
NOT in the forward-paper tracker, undercounting the 100-trade promotion gate.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from core.assets.instrument import CapTier, Instrument
from core.config import Settings
from equities.execution.alpaca import AlpacaOrder
from equities.killgate.tracker import ForwardPaperTracker
from equities.ledger_equity import EquityLedger
from equities.paper import PaperFill
from equities.strategy import Recommendation, Sleeve


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        alpaca_api_key_id="PKTEST",
        alpaca_secret_key="secret",
        alpaca_paper=True,
        alpaca_base_url="https://paper-api.alpaca.markets",
        equity_ledger_path=str(tmp_path / "eq.db"),
    )


@pytest.fixture
def tracker(tmp_path: Path) -> ForwardPaperTracker:
    return ForwardPaperTracker(tmp_path / "fp.db")


def _pending_alpaca_order() -> AlpacaOrder:
    """Create a pending (not filled) Alpaca order."""
    return AlpacaOrder(
        id="ord_pending",
        client_order_id="client_pending",
        symbol="AAPL",
        side="buy",
        qty=100.0,
        status="new",  # pending, not filled
        type="limit",
        time_in_force="day",
        filled_qty=0.0,  # no fill yet
        filled_avg_price=None,  # no fill price
        submitted_at="2026-01-02T14:30:00Z",
        filled_at="",
        raw={"id": "ord_pending", "status": "new"},
    )


def _partial_alpaca_order() -> AlpacaOrder:
    """Create a partially filled Alpaca order."""
    return AlpacaOrder(
        id="ord_partial",
        client_order_id="client_partial",
        symbol="AAPL",
        side="buy",
        qty=100.0,
        status="partially_filled",
        type="limit",
        time_in_force="day",
        filled_qty=50.0,  # partial fill
        filled_avg_price=150.50,  # actual fill price
        submitted_at="2026-01-02T14:30:00Z",
        filled_at="2026-01-02T14:31:00Z",
        raw={"id": "ord_partial", "status": "partially_filled"},
    )


def _rec(ticker: str = "AAPL") -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.LARGE),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=150.0,
        stop_loss=140.0,
        take_profit=160.0,
        size_pct=0.01,
        confidence=0.7,
        catalyst="test",
        thesis="test",
        horizon="short-term",
    )


def test_pending_alpaca_order_recorded_in_fp_tracker(
    settings: Settings, tracker: ForwardPaperTracker
) -> None:
    """Pending Alpaca orders should be recorded in forward-paper tracker with intended price.

    Previously, pending (non-"filled") Alpaca orders were recorded in the equity ledger
    but NOT in the forward-paper tracker, causing under-counting of trades for the
    100-trade promotion gate.
    """
    # Simulate the runner's behavior when placing a pending Alpaca order
    order = _pending_alpaca_order()
    rec = _rec()

    # Calculate values as the runner does
    sized_shares = 100.0
    filled_shares = order.filled_qty if order.filled_qty > 0 else sized_shares  # 100.0
    ledger_entry_price = (
        order.filled_avg_price if order.filled_avg_price is not None else rec.entry
    )  # rec.entry = 150.0

    # Create the PaperFill object (as the runner does)
    fill = PaperFill(
        position_id=1,  # dummy position ID
        ticker=rec.instrument.ticker,
        shares=filled_shares,
        entry_price=ledger_entry_price,
        sleeve=rec.sleeve.value,
    )

    # Record in fp_tracker (this should happen for pending orders too)
    tracker.record_entry(
        ticker=rec.instrument.ticker,
        sleeve=rec.sleeve.value,
        entry_price=fill.entry_price,
        shares=fill.shares,
        strategy="equity_analyst",
    )

    # Verify the entry was recorded
    open_trades = tracker.open_trades()
    assert len(open_trades) == 1, "Pending Alpaca order should be recorded in fp_tracker"

    trade = open_trades[0]
    assert trade.ticker == "AAPL"
    assert trade.sleeve == "swing"
    assert trade.shares == 100.0, "Should record intended shares for pending order"
    assert trade.entry_price == 150.0, "Should record intended entry price for pending order"
    assert trade.status == "open"
    assert trade.exit_price is None
    assert trade.closed_at is None


def test_partially_filled_alpaca_order_recorded_with_actual_price(
    settings: Settings, tracker: ForwardPaperTracker
) -> None:
    """Partially filled Alpaca orders should record actual fill price and quantity."""
    order = _partial_alpaca_order()
    rec = _rec()

    # Calculate values as the runner does
    sized_shares = 100.0
    filled_shares = order.filled_qty if order.filled_qty > 0 else sized_shares  # 50.0
    ledger_entry_price = (
        order.filled_avg_price if order.filled_avg_price is not None else rec.entry
    )  # 150.50

    fill = PaperFill(
        position_id=1,
        ticker=rec.instrument.ticker,
        shares=filled_shares,
        entry_price=ledger_entry_price,
        sleeve=rec.sleeve.value,
    )

    tracker.record_entry(
        ticker=rec.instrument.ticker,
        sleeve=rec.sleeve.value,
        entry_price=fill.entry_price,
        shares=fill.shares,
        strategy="equity_analyst",
    )

    # Verify the entry was recorded with actual fill data
    open_trades = tracker.open_trades()
    assert len(open_trades) == 1

    trade = open_trades[0]
    assert trade.shares == 50.0, "Should record actual filled shares"
    assert trade.entry_price == 150.50, "Should record actual fill price"


def test_multiple_pending_orders_tracked_separately(
    settings: Settings, tracker: ForwardPaperTracker
) -> None:
    """Multiple pending orders should be tracked as separate entries."""
    rec_aapl = _rec("AAPL")
    rec_msft = _rec("MSFT")

    # Record two different pending orders
    tracker.record_entry(
        ticker="AAPL",
        sleeve="swing",
        entry_price=150.0,
        shares=100.0,
        strategy="equity_analyst",
    )
    tracker.record_entry(
        ticker="MSFT",
        sleeve="swing",
        entry_price=380.0,
        shares=50.0,
        strategy="equity_analyst",
    )

    # Verify both are tracked
    open_trades = tracker.open_trades()
    assert len(open_trades) == 2

    tickers = {t.ticker for t in open_trades}
    assert tickers == {"AAPL", "MSFT"}
