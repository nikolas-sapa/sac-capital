import json

import httpx
import pytest

from core.assets.instrument import CapTier, Instrument
from core.config import Settings
from equities.execution.alpaca import AlpacaPaperExecutor, client_order_id_for
from equities.strategy import Recommendation, Sleeve


def _settings(**overrides):
    values = {
        "alpaca_api_key_id": "PKTEST",
        "alpaca_secret_key": "secret",
        "alpaca_paper": True,
        "alpaca_base_url": "https://paper-api.alpaca.markets",
    }
    values.update(overrides)
    return Settings(**values)


def _rec() -> Recommendation:
    return Recommendation(
        instrument=Instrument("AMAT", "Applied Materials", "NASDAQ", CapTier.LARGE),
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


def test_refuses_non_paper_settings():
    with pytest.raises(ValueError, match="ALPACA_PAPER"):
        AlpacaPaperExecutor(_settings(alpaca_paper=False))


def test_refuses_non_paper_base_url():
    with pytest.raises(ValueError, match="non-paper"):
        AlpacaPaperExecutor(_settings(alpaca_base_url="https://api.alpaca.markets"))


def test_accepts_dashboard_v2_endpoint():
    executor = AlpacaPaperExecutor(_settings(alpaca_base_url="https://paper-api.alpaca.markets/v2"))
    assert executor is not None


def test_buy_checks_account_and_submits_limit_order_with_client_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/account":
            return httpx.Response(
                200,
                json={
                    "id": "acct_1",
                    "status": "ACTIVE",
                    "currency": "USD",
                    "buying_power": "1000",
                    "portfolio_value": "1000",
                    "trading_blocked": False,
                    "account_blocked": False,
                },
            )
        seen["headers"] = request.headers
        seen["json"] = json.loads(request.read().decode())
        return httpx.Response(
            200,
            json={
                "id": "ord_123",
                "client_order_id": "client_abc",
                "symbol": "AMAT",
                "side": "buy",
                "qty": "0.123456",
                "status": "accepted",
                "type": "limit",
                "limit_price": "100.00",
                "time_in_force": "day",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    order = AlpacaPaperExecutor(_settings(), client=client).buy(
        _rec(),
        0.123456,
        client_order_id="client_abc",
        max_notional=25.0,
    )

    assert order.id == "ord_123"
    assert order.status == "accepted"
    assert seen["json"]["symbol"] == "AMAT"
    assert seen["json"]["side"] == "buy"
    assert seen["json"]["type"] == "limit"
    assert seen["json"]["limit_price"] == "100.00"
    assert seen["json"]["client_order_id"] == "client_abc"
    assert seen["json"]["time_in_force"] == "day"
    assert seen["headers"]["APCA-API-KEY-ID"] == "PKTEST"


def test_client_order_id_is_stable_for_same_signal():
    rec = _rec()

    assert client_order_id_for(rec, 0.123456) == client_order_id_for(rec, 0.123456)
    assert client_order_id_for(rec, 0.123456).startswith("eq-buy-AMAT-")


def test_buy_rejects_when_notional_exceeds_local_guard():
    executor = AlpacaPaperExecutor(_settings())

    with pytest.raises(ValueError, match="exceeds max_notional"):
        executor.buy(_rec(), 1.0, max_notional=25.0)


def test_buy_rejects_when_buying_power_is_insufficient():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/account"
        return httpx.Response(
            200,
            json={
                "id": "acct_1",
                "status": "ACTIVE",
                "currency": "USD",
                "buying_power": "1",
                "portfolio_value": "1000",
                "trading_blocked": False,
                "account_blocked": False,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    executor = AlpacaPaperExecutor(_settings(), client=client)

    with pytest.raises(RuntimeError, match="buying power"):
        executor.buy(_rec(), 0.5, max_notional=100.0)


def test_get_order_normalizes_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "id": "ord_123",
                "client_order_id": "client_123",
                "symbol": "AMAT",
                "side": "buy",
                "qty": "0.123456",
                "filled_qty": "0.100000",
                "filled_avg_price": "101.23",
                "status": "partially_filled",
                "type": "market",
                "time_in_force": "day",
                "submitted_at": "2026-06-05T13:30:00Z",
                "filled_at": None,
                "canceled_at": None,
                "expired_at": None,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    order = AlpacaPaperExecutor(_settings(), client=client).get_order("ord_123")

    assert seen == {"method": "GET", "path": "/v2/orders/ord_123"}
    assert order.id == "ord_123"
    assert order.symbol == "AMAT"
    assert order.qty == 0.123456
    assert order.filled_qty == 0.1
    assert order.filled_avg_price == 101.23
    assert order.status == "partially_filled"
    assert order.submitted_at == "2026-06-05T13:30:00Z"
    assert order.raw is not None


def test_list_orders_uses_status_and_limit():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "ord_1",
                    "client_order_id": "client_1",
                    "symbol": "AMAT",
                    "side": "buy",
                    "qty": "1",
                    "filled_qty": "1",
                    "filled_avg_price": "100",
                    "status": "filled",
                    "type": "market",
                    "time_in_force": "day",
                },
                {
                    "id": "ord_2",
                    "client_order_id": "client_2",
                    "symbol": "LRCX",
                    "side": "buy",
                    "qty": "2",
                    "filled_qty": "0",
                    "filled_avg_price": None,
                    "status": "accepted",
                    "type": "market",
                    "time_in_force": "day",
                },
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    orders = AlpacaPaperExecutor(_settings(), client=client).list_orders(status="open", limit=2)

    assert seen == {
        "method": "GET",
        "path": "/v2/orders",
        "params": {"status": "open", "limit": "2"},
    }
    assert [order.id for order in orders] == ["ord_1", "ord_2"]
    assert orders[0].filled_avg_price == 100.0
    assert orders[1].filled_avg_price is None


def test_list_positions_normalizes_payloads():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json=[
                {
                    "asset_id": "asset_amat",
                    "symbol": "AMAT",
                    "qty": "0.5",
                    "side": "long",
                    "market_value": "51.25",
                    "avg_entry_price": "100.00",
                    "current_price": "102.50",
                    "unrealized_pl": "1.25",
                }
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    positions = AlpacaPaperExecutor(_settings(), client=client).list_positions()

    assert seen == {"method": "GET", "path": "/v2/positions"}
    assert len(positions) == 1
    assert positions[0].symbol == "AMAT"
    assert positions[0].qty == 0.5
    assert positions[0].market_value == 51.25
    assert positions[0].avg_entry_price == 100.0
    assert positions[0].current_price == 102.5
    assert positions[0].unrealized_pl == 1.25
    assert positions[0].raw is not None


def test_cancel_order_sends_delete():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    AlpacaPaperExecutor(_settings(), client=client).cancel_order("ord_123")

    assert seen == {"method": "DELETE", "path": "/v2/orders/ord_123"}


def test_read_methods_raise_on_broker_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    executor = AlpacaPaperExecutor(_settings(), client=client)

    with pytest.raises(RuntimeError, match="get order failed"):
        executor.get_order("missing")
