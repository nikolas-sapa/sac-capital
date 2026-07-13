"""ticker_active_today — idempotency guard against same-day duplicate buys."""
from datetime import datetime, timezone

from equities.ledger_equity import EquityLedger
from tests.equities.test_ledger_high_water import _rec


def test_active_position_today_is_detected(tmp_path):
    ledger = EquityLedger(tmp_path / "eq.db")
    today = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    ledger.open_position(_rec(), 10.0, 100.0, today, mode="paper")
    assert ledger.ticker_active_today("TEST", "2026-07-13") is True
    # different day -> not blocked (DCA add allowed)
    assert ledger.ticker_active_today("TEST", "2026-07-14") is False
    # different ticker -> not blocked
    assert ledger.ticker_active_today("OTHER", "2026-07-13") is False


def test_closed_position_does_not_block(tmp_path):
    ledger = EquityLedger(tmp_path / "eq.db")
    today = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    pid = ledger.open_position(_rec(), 10.0, 100.0, today, mode="paper")
    ledger.close_position(pid, exit_price=105.0, exit_reason="target_hit", closed_at=today)
    # a same-day position that already closed should not block a re-entry
    assert ledger.ticker_active_today("TEST", "2026-07-13") is False
