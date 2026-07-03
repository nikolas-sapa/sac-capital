from datetime import datetime

import pytest

from core.assets.instrument import CapTier, Instrument
from core.config import Settings
from equities.ledger_equity import EquityLedger
from equities.strategy import Recommendation, Sleeve


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


def _open(ledger, ticker: str, status: str, broker_order_id: str, opened_at: datetime = None) -> int:
    """Helper to open a position with specified status."""
    if opened_at is None:
        opened_at = datetime(2026, 1, 2, 14, 30)
    rec = _rec(ticker)
    return ledger.open_position(
        rec,
        shares=5.0,
        fill_price=100.0,
        opened_at=opened_at,
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id=broker_order_id,
        broker_client_order_id=f"client_{broker_order_id}",
        broker_order_status="accepted",
        status=status,
    )


def test_rejected_orders_do_not_consume_daily_cap(equity_ledger_factory):
    """Test that rejected orders do not consume the daily cap."""
    ledger = equity_ledger_factory()
    _open(ledger, ticker="AAA", status="rejected", broker_order_id="x1")
    _open(ledger, ticker="BBB", status="open", broker_order_id="x2")
    assert ledger.broker_orders_opened_on("2026-01-02") == 1
    ledger.close()


def test_void_orders_do_not_consume_daily_cap(equity_ledger_factory):
    """Test that void orders do not consume the daily cap."""
    ledger = equity_ledger_factory()
    _open(ledger, ticker="AAA", status="void", broker_order_id="x1")
    _open(ledger, ticker="BBB", status="open", broker_order_id="x2")
    assert ledger.broker_orders_opened_on("2026-01-02") == 1
    ledger.close()


def test_both_void_and_rejected_excluded_from_cap(equity_ledger_factory):
    """Test that both void and rejected orders are excluded from daily cap."""
    ledger = equity_ledger_factory()
    _open(ledger, ticker="AAA", status="rejected", broker_order_id="x1")
    _open(ledger, ticker="BBB", status="void", broker_order_id="x2")
    _open(ledger, ticker="CCC", status="open", broker_order_id="x3")
    _open(ledger, ticker="DDD", status="submitted", broker_order_id="x4")
    assert ledger.broker_orders_opened_on("2026-01-02") == 2
    ledger.close()


def test_daily_cap_still_counts_submitted(equity_ledger_factory):
    """Test that submitted orders still count toward daily cap."""
    ledger = equity_ledger_factory()
    _open(ledger, ticker="AAA", status="submitted", broker_order_id="x1")
    _open(ledger, ticker="BBB", status="submitted", broker_order_id="x2")
    assert ledger.broker_orders_opened_on("2026-01-02") == 2
    ledger.close()


def test_daily_cap_scoped_by_date(equity_ledger_factory):
    """Test that daily cap is scoped to the specified date."""
    ledger = equity_ledger_factory()
    today = datetime(2026, 1, 2, 14, 30)
    tomorrow = datetime(2026, 1, 3, 14, 30)

    _open(ledger, ticker="AAA", status="open", broker_order_id="x1", opened_at=today)
    _open(ledger, ticker="BBB", status="rejected", broker_order_id="x2", opened_at=today)
    _open(ledger, ticker="CCC", status="open", broker_order_id="x3", opened_at=tomorrow)

    assert ledger.broker_orders_opened_on("2026-01-02") == 1
    assert ledger.broker_orders_opened_on("2026-01-03") == 1
    ledger.close()
