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


def test_open_position_records_sector(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(
        _rec(),
        shares=5.0,
        fill_price=10.0,
        opened_at=datetime(2026, 1, 2, 14, 30),
        mode="paper",
        sector="Technology",
    )

    assert led.open_positions()[0]["sector"] == "Technology"
    assert "Technology" in (tmp_path / "eq.csv").read_text()
    led.close()


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


def test_realized_pnl_on_filters_by_close_day(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    first = led.open_position(_rec(), shares=5.0, fill_price=10.0,
                              opened_at=datetime(2026, 1, 2), mode="paper")
    second = led.open_position(_rec(), shares=5.0, fill_price=10.0,
                               opened_at=datetime(2026, 1, 2), mode="paper")
    led.close_position(first, exit_price=8.0, exit_reason="stop",
                       closed_at=datetime(2026, 1, 5, 15, 0))
    led.close_position(second, exit_price=13.0, exit_reason="target",
                       closed_at=datetime(2026, 1, 6, 15, 0))

    assert led.realized_pnl_on("2026-01-05") == -10.0
    assert led.realized_pnl_on("2026-01-06") == 15.0
    led.close()


def test_void_position_removes_from_open_without_pnl(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    pid = led.open_position(_rec(), shares=5.0, fill_price=10.0,
                            opened_at=datetime(2026, 1, 2), mode="paper")
    led.void_position(pid, reason="broker_expired_unfilled", closed_at=datetime(2026, 1, 3))
    assert led.open_positions() == []
    assert led.realized_pnl() == 0.0
    assert "broker_expired_unfilled" in (tmp_path / "eq.csv").read_text()
    led.close()


def test_csv_mirror_written(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=5.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2), mode="paper", strategy="swing_v1")
    csv_path = (tmp_path / "eq.csv")
    assert csv_path.exists()
    assert "ACME" in csv_path.read_text()
    led.close()


def test_open_position_records_broker_metadata(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(
        _rec(),
        shares=5.0,
        fill_price=10.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        strategy="swing_v1",
        execution_provider="alpaca_paper",
        broker_order_id="ord_123",
        broker_client_order_id="client_123",
        broker_order_status="accepted",
        status="submitted",
    )
    pos = led.open_positions()[0]
    assert pos["status"] == "submitted"
    assert pos["execution_provider"] == "alpaca_paper"
    assert pos["broker_order_id"] == "ord_123"
    assert pos["broker_client_order_id"] == "client_123"
    assert pos["broker_order_status"] == "accepted"
    assert led.position_by_broker_client_order_id("client_123")["id"] == pos["id"]
    assert "ord_123" in (tmp_path / "eq.csv").read_text()
    led.close()


def test_update_broker_order_records_fill_state(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    pid = led.open_position(
        _rec(),
        shares=5.0,
        fill_price=10.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_123",
        broker_client_order_id="client_123",
        broker_order_status="accepted",
        status="submitted",
    )
    led.update_broker_order(
        pid,
        broker_order_status="filled",
        broker_filled_qty=5.0,
        broker_avg_fill_price=10.25,
        status="open",
        entry_price=10.25,
        shares=5.0,
        broker_submitted_at="2026-01-02T14:30:00Z",
        broker_filled_at="2026-01-02T14:30:01Z",
        broker_raw_json='{"id":"ord_123"}',
    )

    pos = led.position_by_broker_order_id("ord_123")
    assert pos is not None
    assert pos["broker_order_status"] == "filled"
    assert pos["broker_filled_qty"] == 5.0
    assert pos["broker_avg_fill_price"] == 10.25
    assert pos["entry_price"] == 10.25
    assert pos["mark_price"] == 10.25
    assert pos["status"] == "open"
    assert pos["broker_filled_at"] == "2026-01-02T14:30:01Z"
    assert pos["broker_raw_json"] == '{"id":"ord_123"}'
    assert "ord_123" in (tmp_path / "eq.csv").read_text()
    led.close()


def test_broker_orders_opened_on_counts_only_matching_provider_and_day(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(
        _rec(),
        shares=5.0,
        fill_price=10.0,
        opened_at=datetime(2026, 1, 2, 14, 30),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_1",
        broker_client_order_id="client_1",
    )
    led.open_position(
        _rec(),
        shares=5.0,
        fill_price=10.0,
        opened_at=datetime(2026, 1, 2, 15, 30),
        mode="paper",
        execution_provider="internal_paper",
        broker_order_id="ord_2",
    )
    led.open_position(
        _rec(),
        shares=5.0,
        fill_price=10.0,
        opened_at=datetime(2026, 1, 3, 14, 30),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_3",
    )

    assert led.broker_orders_opened_on("2026-01-02") == 1
    led.close()


def test_close_position_raises_on_missing_position(tmp_path):
    """Test that closing a non-existent position raises ValueError."""
    led = EquityLedger(tmp_path / "eq.db")
    try:
        # Try to close position ID 999 which doesn't exist
        led.close_position(999, exit_price=13.0, exit_reason="test",
                           closed_at=datetime(2026, 1, 5))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Position 999 not found" in str(e)
    finally:
        led.close()


def test_reduce_position_partial_keeps_remainder_open(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=10.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2, 14, 30), mode="paper", strategy="swing_v1")
    pid = led.open_positions()[0]["id"]
    sold = led.reduce_position(pid, 4.0, 12.0, "concentration_trim", datetime(2026, 1, 5, 14, 30))
    assert sold == 4.0
    open_pos = led.open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["shares"] == 6.0
    # realized banked on the sold slice only: (12 - 10) * 4
    assert led.realized_pnl() == 8.0
    led.close()


def test_reduce_position_full_closes_the_lot(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=10.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2, 14, 30), mode="paper", strategy="swing_v1")
    pid = led.open_positions()[0]["id"]
    sold = led.reduce_position(pid, 10.0, 12.0, "concentration_trim", datetime(2026, 1, 5, 14, 30))
    assert sold == 10.0
    assert led.open_positions() == []
    assert led.realized_pnl() == 20.0
    led.close()


def test_reduce_position_caps_at_lot_size(tmp_path):
    """Asking for more than the lot holds reduces the lot, never goes negative."""
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=3.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2, 14, 30), mode="paper", strategy="swing_v1")
    pid = led.open_positions()[0]["id"]
    sold = led.reduce_position(pid, 9.0, 11.0, "concentration_trim", datetime(2026, 1, 5, 14, 30))
    assert sold == 3.0
    assert led.open_positions() == []
    led.close()


def test_reduce_position_does_not_clone_broker_order_ids(tmp_path):
    """The closed slice must not carry the dedup key, or reruns skip live orders."""
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=10.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2, 14, 30), mode="paper", strategy="swing_v1",
                      broker_client_order_id="eq-buy-ACME-deadbeef")
    pid = led.open_positions()[0]["id"]
    led.reduce_position(pid, 4.0, 12.0, "concentration_trim", datetime(2026, 1, 5, 14, 30))
    found = led.position_by_broker_client_order_id("eq-buy-ACME-deadbeef")
    assert found is not None
    assert found["id"] == pid
    assert found["status"] == "open"
    led.close()
