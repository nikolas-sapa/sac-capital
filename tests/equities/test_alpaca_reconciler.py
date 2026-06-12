from datetime import datetime

from core.assets.instrument import CapTier, Instrument
from core.config import Settings
from equities.execution.alpaca import AlpacaOrder, AlpacaPosition
from equities.execution.reconciler import reconcile_alpaca
from equities.ledger_equity import EquityLedger
from equities.strategy import Recommendation, Sleeve


def _settings(tmp_path) -> Settings:
    return Settings(
        alpaca_api_key_id="PKTEST",
        alpaca_secret_key="secret",
        alpaca_paper=True,
        alpaca_base_url="https://paper-api.alpaca.markets",
        equity_ledger_path=str(tmp_path / "eq.db"),
    )


def _rec(ticker: str = "AMAT") -> Recommendation:
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


class FakeExecutor:
    def __init__(self, orders, positions=None):
        self._orders = orders
        self._positions = positions or []

    def list_positions(self):
        return self._positions

    def get_order(self, order_id):
        return self._orders[order_id]


def _order(status: str, filled_qty: float = 0.0) -> AlpacaOrder:
    return AlpacaOrder(
        id="ord_123",
        client_order_id="client_123",
        symbol="AMAT",
        side="buy",
        qty=1.0,
        status=status,
        type="market",
        time_in_force="day",
        filled_qty=filled_qty,
        filled_avg_price=101.0 if filled_qty else None,
        submitted_at="2026-01-02T14:30:00Z",
        filled_at="2026-01-02T14:31:00Z" if filled_qty else "",
        raw={"id": "ord_123", "status": status},
    )


def test_reconcile_updates_filled_order(tmp_path):
    settings = _settings(tmp_path)
    ledger = EquityLedger(settings.equity_ledger_path)
    pid = ledger.open_position(
        _rec(),
        shares=1.0,
        fill_price=100.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_123",
        broker_client_order_id="client_123",
        broker_order_status="accepted",
        status="submitted",
    )
    executor = FakeExecutor(
        {"ord_123": _order("filled", filled_qty=1.0)},
        positions=[
            AlpacaPosition(
                asset_id="asset_1",
                symbol="AMAT",
                qty=1.0,
                side="long",
                market_value=101.0,
                avg_entry_price=101.0,
            )
        ],
    )

    result = reconcile_alpaca(settings, executor=executor, ledger=ledger, log_path=tmp_path / "r.log")

    pos = ledger.position_by_broker_order_id("ord_123")
    assert result.orders_checked == 1
    assert result.orders_updated == 1
    assert result.mismatches == []
    assert pos["broker_order_status"] == "filled"
    assert pos["broker_filled_qty"] == 1.0
    assert pos["broker_avg_fill_price"] == 101.0
    assert pos["entry_price"] == 101.0
    assert pos["mark_price"] == 101.0
    assert pos["status"] == "open"
    assert '"orders_checked": 1' in (tmp_path / "r.log").read_text()
    ledger.close()


def test_reconcile_voids_unfilled_expired_order(tmp_path):
    settings = _settings(tmp_path)
    ledger = EquityLedger(settings.equity_ledger_path)
    ledger.open_position(
        _rec(),
        shares=1.0,
        fill_price=100.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_123",
        broker_client_order_id="client_123",
        broker_order_status="accepted",
        status="submitted",
    )
    executor = FakeExecutor({"ord_123": _order("expired", filled_qty=0.0)})

    result = reconcile_alpaca(settings, executor=executor, ledger=ledger, log_path=tmp_path / "r.log")

    assert result.positions_voided == 1
    assert ledger.open_positions() == []
    assert ledger.position_by_broker_client_order_id("client_123")["status"] == "expired"
    assert "broker_expired_unfilled" in (tmp_path / "eq.csv").read_text()
    ledger.close()


def test_reconcile_reports_missing_broker_position_for_filled_order(tmp_path):
    settings = _settings(tmp_path)
    ledger = EquityLedger(settings.equity_ledger_path)
    ledger.open_position(
        _rec(),
        shares=1.0,
        fill_price=100.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_123",
        broker_client_order_id="client_123",
        broker_order_status="accepted",
        status="submitted",
    )
    executor = FakeExecutor({"ord_123": _order("filled", filled_qty=1.0)})

    result = reconcile_alpaca(settings, executor=executor, ledger=ledger, log_path=tmp_path / "r.log")

    assert result.mismatches == ["AMAT: filled_order_missing_broker_position"]
    ledger.close()


def test_reconcile_compares_aggregate_lots_to_broker_position(tmp_path):
    settings = _settings(tmp_path)
    ledger = EquityLedger(settings.equity_ledger_path)
    first_id = ledger.open_position(
        _rec("MSFT"),
        shares=1.0,
        fill_price=100.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_1",
        broker_client_order_id="client_1",
        broker_order_status="accepted",
        status="submitted",
    )
    second_id = ledger.open_position(
        _rec("MSFT"),
        shares=2.0,
        fill_price=101.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_2",
        broker_client_order_id="client_2",
        broker_order_status="accepted",
        status="submitted",
    )
    pending_id = ledger.open_position(
        _rec("MSFT"),
        shares=3.0,
        fill_price=102.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_3",
        broker_client_order_id="client_3",
        broker_order_status="accepted",
        status="submitted",
    )

    executor = FakeExecutor(
        {
            "ord_1": AlpacaOrder(
                id="ord_1",
                client_order_id="client_1",
                symbol="MSFT",
                side="buy",
                qty=1.0,
                status="filled",
                type="market",
                time_in_force="day",
                filled_qty=1.0,
                filled_avg_price=100.0,
            ),
            "ord_2": AlpacaOrder(
                id="ord_2",
                client_order_id="client_2",
                symbol="MSFT",
                side="buy",
                qty=2.0,
                status="filled",
                type="market",
                time_in_force="day",
                filled_qty=2.0,
                filled_avg_price=101.0,
            ),
            "ord_3": AlpacaOrder(
                id="ord_3",
                client_order_id="client_3",
                symbol="MSFT",
                side="buy",
                qty=3.0,
                status="new",
                type="limit",
                time_in_force="day",
                filled_qty=0.0,
                filled_avg_price=None,
            ),
        },
        positions=[
            AlpacaPosition(
                asset_id="asset_1",
                symbol="MSFT",
                qty=3.0,
                side="long",
                market_value=303.0,
                avg_entry_price=101.0,
            )
        ],
    )

    result = reconcile_alpaca(settings, executor=executor, ledger=ledger, log_path=tmp_path / "r.log")

    assert result.orders_checked == 3
    assert result.mismatches == []
    assert ledger.open_positions()[0]["id"] == first_id
    assert ledger.open_positions()[1]["id"] == second_id
    assert ledger.open_positions()[2]["id"] == pending_id
    assert ledger.position_by_broker_order_id("ord_3")["status"] == "submitted"
    ledger.close()


def test_reconcile_keeps_partially_filled_order_active(tmp_path):
    settings = _settings(tmp_path)
    ledger = EquityLedger(settings.equity_ledger_path)
    ledger.open_position(
        _rec(),
        shares=1.0,
        fill_price=100.0,
        opened_at=datetime(2026, 1, 2),
        mode="paper",
        execution_provider="alpaca_paper",
        broker_order_id="ord_123",
        broker_client_order_id="client_123",
        broker_order_status="accepted",
        status="submitted",
    )
    executor = FakeExecutor(
        {"ord_123": _order("partially_filled", filled_qty=0.4)},
        positions=[
            AlpacaPosition(
                asset_id="asset_1",
                symbol="AMAT",
                qty=0.4,
                side="long",
                market_value=40.4,
                avg_entry_price=101.0,
            )
        ],
    )

    result = reconcile_alpaca(settings, executor=executor, ledger=ledger, log_path=tmp_path / "r.log")

    pos = ledger.position_by_broker_client_order_id("client_123")
    assert result.positions_voided == 0
    assert pos["status"] == "partially_filled"
    assert pos["broker_filled_qty"] == 0.4
    assert ledger.open_positions()[0]["id"] == pos["id"]
    ledger.close()
