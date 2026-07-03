from datetime import datetime

import pytest

from core.assets.instrument import CapTier, Instrument
from core.config import Settings
from equities.ledger_equity import EquityLedger
from equities.strategy import Recommendation, Sleeve


@pytest.fixture
def tmp_path_obj(tmp_path):
    """Provide tmp_path as a fixture for tests that don't have it injected."""
    return tmp_path


@pytest.fixture
def equity_ledger_factory(tmp_path):
    """Factory fixture for creating EquityLedger instances."""
    def _create_ledger():
        settings = Settings(
            alpaca_api_key_id="PKTEST",
            alpaca_secret_key="secret",
            alpaca_paper=True,
            alpaca_base_url="https://paper-api.alpaca.markets",
            equity_ledger_path=str(tmp_path / "eq.db"),
        )
        return EquityLedger(settings.equity_ledger_path)
    return _create_ledger


def _rec(ticker: str = "AAA") -> Recommendation:
    """Create a test recommendation."""
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.LARGE),
        sleeve=Sleeve.CORE,
        side="buy",
        entry=100.0,
        stop_loss=None,
        take_profit=None,
        size_pct=0.01,
        confidence=0.7,
        catalyst="test",
        thesis="test",
        horizon="long-term",
    )


def _open(ledger, ticker: str, shares: float, entry: float, status: str) -> int:
    """Helper to open a position with specified status."""
    rec = _rec(ticker)
    return ledger.open_position(
        rec,
        shares=shares,
        fill_price=entry,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id=f"ord_{ticker}",
        broker_client_order_id=f"client_{ticker}",
        broker_order_status="accepted",
        status=status,
    )


def test_pending_notional_sums_submitted_positions(equity_ledger_factory):
    """Test that pending_notional() sums shares*entry_price for status='submitted'."""
    ledger = equity_ledger_factory()
    # open one submitted and one open position via the same helper other ledger tests use
    _open(ledger, ticker="AAA", shares=10, entry=100.0, status="submitted")
    _open(ledger, ticker="BBB", shares=5, entry=50.0, status="open")
    assert ledger.pending_notional() == 1000.0
    ledger.close()


def test_pending_notional_ignores_non_submitted(equity_ledger_factory):
    """Test that pending_notional() ignores open, closed, and void positions."""
    ledger = equity_ledger_factory()
    _open(ledger, ticker="AAA", shares=10, entry=100.0, status="submitted")
    _open(ledger, ticker="BBB", shares=5, entry=50.0, status="open")
    _open(ledger, ticker="CCC", shares=2, entry=75.0, status="closed")
    _open(ledger, ticker="DDD", shares=1, entry=200.0, status="void")
    # Only AAA is submitted: 10 * 100.0 = 1000.0
    assert ledger.pending_notional() == 1000.0
    ledger.close()


def test_pending_notional_empty_ledger(equity_ledger_factory):
    """Test that pending_notional() returns 0.0 for empty ledger."""
    ledger = equity_ledger_factory()
    assert ledger.pending_notional() == 0.0
    ledger.close()
