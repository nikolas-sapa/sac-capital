"""Unit tests for core/clob/client.py — pure-function tests only.

All tests exercise _apply_book_message which is a pure parser with no I/O.
No websocket connections are made; these run fully offline.
"""

from __future__ import annotations

import pytest

from core.clob.client import OrderBook, _apply_book_message


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
