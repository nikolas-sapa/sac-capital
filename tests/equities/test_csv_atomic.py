"""Test atomic CSV mirror writes."""
import csv
from datetime import datetime

import pytest

from core.assets.instrument import CapTier, Instrument
from core.config import Settings
from equities.ledger_equity import EquityLedger
from equities.strategy import Recommendation, Sleeve


@pytest.fixture
def equity_ledger_factory(tmp_path):
    """Factory fixture for creating EquityLedger instances."""
    def _create_ledger(csv_path=None):
        settings = Settings(
            alpaca_api_key_id="PKTEST",
            alpaca_secret_key="secret",
            alpaca_paper=True,
            alpaca_base_url="https://paper-api.alpaca.markets",
            equity_ledger_path=str(csv_path.with_suffix(".db") if csv_path else tmp_path / "eq.db"),
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


def test_rewrite_csv_leaves_no_tmp_and_valid_csv(tmp_path):
    """Test that _rewrite_csv leaves no tmp file and CSV is valid."""
    csv_path = tmp_path / "positions.csv"
    settings = Settings(
        alpaca_api_key_id="PKTEST",
        alpaca_secret_key="secret",
        alpaca_paper=True,
        alpaca_base_url="https://paper-api.alpaca.markets",
        equity_ledger_path=str(csv_path.with_suffix(".db")),
    )
    ledger = EquityLedger(settings.equity_ledger_path)
    _open(ledger, ticker="AAA", shares=1, entry=10.0, status="open")

    # After open_position, which calls _rewrite_csv, tmp file should not exist
    tmp_file = csv_path.with_suffix(csv_path.suffix + ".tmp")
    assert not tmp_file.exists(), f"Temporary file {tmp_file} should not exist after write"

    # CSV should exist and be valid
    assert csv_path.exists(), f"CSV file {csv_path} should exist"

    # Read CSV and verify content
    rows = list(csv.DictReader(open(csv_path)))
    assert len(rows) > 0, "CSV should have at least one row"
    assert rows[0]["ticker"] == "AAA", "First row should have ticker AAA"

    ledger.close()
