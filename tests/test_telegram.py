"""Tests for core.alerts.telegram — no network hits."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from core.alerts.telegram import TelegramAlerts
from core.execution.base import Fill
from core.markets import Market, Outcome
from core.strategy import Signal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fill() -> Fill:
    outcome = Outcome(token_id="tok-yes", label="Yes", best_bid=0.55, best_ask=0.60)
    market = Market(
        condition_id="cond-abc",
        question="Will ETH exceed $5000 by end of year?",
        outcomes=[outcome],
        end_date=datetime(2025, 12, 31),
        closed=False,
    )
    signal = Signal(
        market=market,
        token_id="tok-yes",
        fair_prob=0.65,
        price=0.60,
        confidence=0.8,
        reason="test",
    )
    return Fill(
        signal=signal,
        stake=50.0,
        shares=83.3333,
        avg_price=0.6001,
        timestamp=datetime(2025, 6, 1, 12, 0, 0),
        mode="paper",
    )


# ---------------------------------------------------------------------------
# format_fill tests (pure — no mocks needed)
# ---------------------------------------------------------------------------

def test_format_fill_contains_paper_fill_header():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "PAPER FILL" in msg


def test_format_fill_contains_question():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "Will ETH exceed $5000 by end of year?" in msg


def test_format_fill_contains_outcome_label():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "Yes" in msg


def test_format_fill_contains_stake():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "50.00" in msg


def test_format_fill_contains_shares():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "83.3333" in msg


def test_format_fill_contains_avg_price():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "0.6001" in msg


def test_format_fill_contains_fair_prob():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "0.650" in msg


def test_format_fill_contains_mode():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "paper" in msg


def test_format_fill_returns_string():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    assert isinstance(alerts.format_fill(fill), str)


# ---------------------------------------------------------------------------
# format_error tests (pure)
# ---------------------------------------------------------------------------

def test_format_error_prefix():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    result = alerts.format_error("something went wrong")
    assert result == "[ERROR] something went wrong"


def test_format_error_returns_string():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    assert isinstance(alerts.format_error("boom"), str)


# ---------------------------------------------------------------------------
# send tests (mock aiogram — no network)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_calls_send_message_once():
    """send() must await bot.send_message with correct args; no real network."""
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()
    # Ensure async context manager works
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=False)

    with patch("core.alerts.telegram.Bot", return_value=mock_bot) as MockBot:
        await alerts.send("hello telegram")

    MockBot.assert_called_once_with("fake-token")
    mock_bot.send_message.assert_awaited_once_with("123456", "hello telegram")


@pytest.mark.asyncio
async def test_send_uses_stored_chat_id():
    """send() uses the chat_id provided at construction."""
    alerts = TelegramAlerts(token="tok", chat_id="999")

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=False)

    with patch("core.alerts.telegram.Bot", return_value=mock_bot):
        await alerts.send("test")

    mock_bot.send_message.assert_awaited_once_with("999", "test")
