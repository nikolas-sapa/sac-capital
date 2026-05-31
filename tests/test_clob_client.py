"""Unit tests for core/clob/client.py — pure-function tests only.

Tests exercise _apply_book_message and _parse_message (pure parsers, no I/O).
No websocket connections are made; these run fully offline.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from core.clob.client import (
    OrderBook,
    _PING_INTERVAL,
    _WS_URL,
    _apply_book_message,
    _keepalive,
    _parse_message,
)


# ---------------------------------------------------------------------------
# Fixtures — captured Polymarket CLOB market-channel "book" message shapes
# ---------------------------------------------------------------------------

BOOK_MSG = {
    "event_type": "book",
    "asset_id": "token-abc-123",
    "market": "condition-xyz",
    "bids": [
        {"price": "0.48", "size": "100"},
        {"price": "0.50", "size": "30"},
    ],
    "asks": [
        {"price": "0.55", "size": "10"},
        {"price": "0.52", "size": "200"},
    ],
    "timestamp": "2024-01-01T00:00:00Z",
    "hash": "abc123",
}

EMPTY_BOOK_MSG = {
    "event_type": "book",
    "asset_id": "token-empty",
    "market": "condition-empty",
    "bids": [],
    "asks": [],
    "timestamp": "2024-01-01T00:00:00Z",
    "hash": "empty",
}


# ---------------------------------------------------------------------------
# Tests for _apply_book_message
# ---------------------------------------------------------------------------


class TestApplyBookMessage:
    def test_asset_id_parsed_correctly(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        assert ob.asset_id == "token-abc-123"

    def test_bids_sorted_descending(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        prices = [price for price, _ in ob.bids]
        assert prices == sorted(prices, reverse=True), "bids must be sorted descending by price"

    def test_asks_sorted_ascending(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        prices = [price for price, _ in ob.asks]
        assert prices == sorted(prices), "asks must be sorted ascending by price"

    def test_best_bid_is_highest_bid(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        assert ob.best_bid == pytest.approx(0.50)

    def test_best_ask_is_lowest_ask(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        assert ob.best_ask == pytest.approx(0.52)

    def test_sizes_parsed_as_floats(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        for _, size in ob.bids:
            assert isinstance(size, float), f"bid size {size!r} must be float"
        for _, size in ob.asks:
            assert isinstance(size, float), f"ask size {size!r} must be float"

    def test_prices_parsed_as_floats(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        for price, _ in ob.bids:
            assert isinstance(price, float), f"bid price {price!r} must be float"
        for price, _ in ob.asks:
            assert isinstance(price, float), f"ask price {price!r} must be float"

    def test_bid_sizes_correct(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        # After descending sort: (0.50, 30.0), (0.48, 100.0)
        assert ob.bids[0] == (pytest.approx(0.50), pytest.approx(30.0))
        assert ob.bids[1] == (pytest.approx(0.48), pytest.approx(100.0))

    def test_ask_sizes_correct(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        # After ascending sort: (0.52, 200.0), (0.55, 10.0)
        assert ob.asks[0] == (pytest.approx(0.52), pytest.approx(200.0))
        assert ob.asks[1] == (pytest.approx(0.55), pytest.approx(10.0))

    def test_orderbook_is_frozen(self) -> None:
        ob = _apply_book_message(BOOK_MSG)
        assert isinstance(ob, OrderBook)
        with pytest.raises((AttributeError, TypeError)):
            ob.asset_id = "modified"  # type: ignore[misc]


class TestApplyBookMessageEmpty:
    def test_empty_bids_returns_empty_list(self) -> None:
        ob = _apply_book_message(EMPTY_BOOK_MSG)
        assert ob.bids == []

    def test_empty_asks_returns_empty_list(self) -> None:
        ob = _apply_book_message(EMPTY_BOOK_MSG)
        assert ob.asks == []

    def test_empty_bids_best_bid_is_zero(self) -> None:
        ob = _apply_book_message(EMPTY_BOOK_MSG)
        assert ob.best_bid == 0.0

    def test_empty_asks_best_ask_is_zero(self) -> None:
        ob = _apply_book_message(EMPTY_BOOK_MSG)
        assert ob.best_ask == 0.0

    def test_empty_asset_id(self) -> None:
        ob = _apply_book_message(EMPTY_BOOK_MSG)
        assert ob.asset_id == "token-empty"


# ---------------------------------------------------------------------------
# Regression: correct websocket host
# ---------------------------------------------------------------------------


class TestWsUrl:
    def test_ws_url_correct_host(self) -> None:
        """Guard against typo in the CLOB websocket hostname."""
        assert _WS_URL == "wss://ws-subscriptions-clob.polymarket.com/ws/market"


# ---------------------------------------------------------------------------
# Tests for _parse_message
# ---------------------------------------------------------------------------


class TestParseMessage:
    def test_valid_book_json_returns_orderbook(self) -> None:
        raw = json.dumps(BOOK_MSG)
        ob = _parse_message(raw)
        assert ob is not None
        assert isinstance(ob, OrderBook)
        assert ob.best_bid == pytest.approx(0.50)
        assert ob.best_ask == pytest.approx(0.52)

    def test_pong_heartbeat_returns_none(self) -> None:
        assert _parse_message("PONG") is None

    def test_ping_heartbeat_returns_none(self) -> None:
        assert _parse_message("PING") is None

    def test_price_change_event_returns_none(self) -> None:
        price_change = json.dumps({
            "event_type": "price_change",
            "asset_id": "token-abc-123",
            "price": "0.51",
            "side": "BUY",
            "timestamp": "2024-01-01T00:00:00Z",
        })
        assert _parse_message(price_change) is None

    def test_malformed_json_returns_none(self) -> None:
        assert _parse_message("{not json") is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_message("") is None

    def test_non_book_dict_returns_none(self) -> None:
        raw = json.dumps({"event_type": "tick_size_change", "asset_id": "x"})
        assert _parse_message(raw) is None


class TestParseMessageBatchList:
    """Polymarket may send a JSON array of events in a single frame."""

    def test_list_with_one_book_event_returns_orderbook(self) -> None:
        batch = json.dumps([BOOK_MSG])
        ob = _parse_message(batch)
        assert ob is not None
        assert ob.asset_id == "token-abc-123"
        assert ob.best_bid == pytest.approx(0.50)

    def test_list_with_non_book_only_returns_none(self) -> None:
        batch = json.dumps([
            {"event_type": "price_change", "asset_id": "x", "price": "0.5"},
        ])
        assert _parse_message(batch) is None

    def test_list_with_mixed_events_returns_first_book(self) -> None:
        batch = json.dumps([
            {"event_type": "price_change", "asset_id": "x"},
            BOOK_MSG,
        ])
        ob = _parse_message(batch)
        assert ob is not None
        assert ob.asset_id == "token-abc-123"

    def test_empty_list_returns_none(self) -> None:
        assert _parse_message("[]") is None


# ---------------------------------------------------------------------------
# Keepalive constant + helper unit tests
# ---------------------------------------------------------------------------


class TestPingInterval:
    def test_ping_interval_value(self) -> None:
        """Module constant must be exactly 10.0 seconds."""
        assert _PING_INTERVAL == 10.0


class TestKeepalive:
    """Unit tests for the _keepalive coroutine using a minimal fake websocket.

    We test _keepalive in isolation — not the full stream() wiring — which
    keeps the test simple and avoids mocking the websockets connect() seam.
    """

    @pytest.mark.asyncio
    async def test_keepalive_sends_ping(self) -> None:
        """_keepalive must call ws.send('PING') at least once."""
        sent: list[str] = []

        class _FakeWS:
            async def send(self, text: str) -> None:
                sent.append(text)

        task = asyncio.create_task(_keepalive(_FakeWS(), interval=0.01))
        await asyncio.sleep(0.05)  # allow 2-3 PINGs to fire
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(sent) >= 1
        assert all(m == "PING" for m in sent)

    @pytest.mark.asyncio
    async def test_keepalive_exits_on_connection_closed(self) -> None:
        """_keepalive must exit quietly when ConnectionClosed is raised by send."""
        from websockets.exceptions import ConnectionClosed

        class _FakeWS:
            async def send(self, text: str) -> None:
                # Simulate server closing the connection on first send.
                raise ConnectionClosed(None, None)  # type: ignore[arg-type]

        # Should complete without raising.
        await asyncio.wait_for(_keepalive(_FakeWS(), interval=0.01), timeout=1.0)

    @pytest.mark.asyncio
    async def test_keepalive_cancellable(self) -> None:
        """_keepalive task must exit cleanly on asyncio.CancelledError."""

        class _FakeWS:
            async def send(self, text: str) -> None:
                pass

        task = asyncio.create_task(_keepalive(_FakeWS(), interval=10.0))
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # expected — task propagates CancelledError out of asyncio.sleep
        # Reaching here means the task terminated without hanging.
