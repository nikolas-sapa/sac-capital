"""Tests for the duplicate order guard and day-scoped client order IDs."""
from datetime import date, datetime, timezone

import pytest

from core.assets.instrument import CapTier, Instrument
from equities.execution.alpaca import client_order_id_for
from equities.strategy import Recommendation, Sleeve
from runner_equities import _should_skip_duplicate


def _rec(ticker: str = "AMAT", **overrides) -> Recommendation:
    """Helper to create a test recommendation."""
    values = {
        "instrument": Instrument(ticker, f"{ticker} Corp", "NASDAQ", CapTier.LARGE),
        "sleeve": Sleeve.CORE,
        "side": "buy",
        "entry": 100.0,
        "stop_loss": None,
        "take_profit": None,
        "size_pct": 0.01,
        "confidence": 0.7,
        "catalyst": "test",
        "thesis": "test",
        "horizon": "long-term",
    }
    values.update(overrides)
    return Recommendation(**values)


def test_rejected_order_blocks_resubmission():
    """A rejected order should prevent resubmission of the same client_order_id."""
    existing_order = {"status": "rejected"}
    assert _should_skip_duplicate(existing_order) is True


def test_active_order_blocks_resubmission():
    """An active (submitted) order should prevent resubmission."""
    existing_order = {"status": "submitted"}
    assert _should_skip_duplicate(existing_order) is True


def test_filled_order_blocks_resubmission():
    """A filled order should prevent resubmission."""
    existing_order = {"status": "filled"}
    assert _should_skip_duplicate(existing_order) is True


def test_no_existing_order_allows_submission():
    """When no order exists, submission should be allowed."""
    assert _should_skip_duplicate(None) is False


def test_client_order_id_is_stable_within_day():
    """Within the same day, identical signals produce identical client_order_ids."""
    rec = _rec()
    id1 = client_order_id_for(rec, 0.123456)
    id2 = client_order_id_for(rec, 0.123456)
    assert id1 == id2


def test_client_order_id_changes_across_days(monkeypatch):
    """Identical signals on different dates produce different client_order_ids.

    This ensures day-scoped idempotency: reusing an ID across days is safe.
    """
    rec = _rec()
    shares = 0.123456

    # Get ID for today
    id_today = client_order_id_for(rec, shares)

    # Monkeypatch datetime.now to return yesterday's date
    class MockDatetime:
        @staticmethod
        def now(tz=None):
            yesterday = datetime.now(tz=tz).replace(day=datetime.now(tz=tz).day - 1)
            return yesterday

    import equities.execution.alpaca
    original_datetime = equities.execution.alpaca.datetime
    try:
        # We need to patch the datetime module in the alpaca execution module
        # to return a different date
        from unittest.mock import patch
        with patch(
            "equities.execution.alpaca.datetime"
        ) as mock_datetime_module:
            mock_datetime_module.now.return_value = datetime(
                datetime.now().year,
                datetime.now().month,
                max(1, datetime.now().day - 1),
                tzinfo=timezone.utc
            )
            id_yesterday = client_order_id_for(rec, shares)

        # Different days should produce different IDs
        assert id_today != id_yesterday
    finally:
        equities.execution.alpaca.datetime = original_datetime
