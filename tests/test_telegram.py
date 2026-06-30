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
    assert "something went wrong" in result


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


# ---------------------------------------------------------------------------
# format_fill — edge field added
# ---------------------------------------------------------------------------

def test_format_fill_contains_edge():
    alerts = TelegramAlerts(token="fake-token", chat_id="123456")
    fill = _make_fill()
    msg = alerts.format_fill(fill)
    assert "Edge:" in msg


# ---------------------------------------------------------------------------
# format_polymarket_scan tests
# ---------------------------------------------------------------------------

def test_format_polymarket_scan_contains_market_count():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_polymarket_scan(500, ["weather", "crypto_updown"])
    assert "500" in msg
    assert "POLYMARKET SCAN" in msg


def test_format_polymarket_scan_contains_strategies():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_polymarket_scan(100, ["weather", "dummy"])
    assert "weather" in msg
    assert "dummy" in msg


# ---------------------------------------------------------------------------
# format_equity_scan tests
# ---------------------------------------------------------------------------

class _FakeInstrument:
    def __init__(self, ticker: str, name: str = "Co"):
        self.ticker = ticker
        self.name = name


class _FakeEventType:
    def __init__(self, value: str):
        self.value = value


class _FakeSwingCandidate:
    def __init__(self, ticker: str, event: str, evidence: str, urgency: float = 0.8, days: int | None = 5):
        self.instrument = _FakeInstrument(ticker)
        self.event_type = _FakeEventType(event)
        self.evidence = evidence
        self.urgency = urgency
        self.days_to_event = days


class _FakeCoreCandidate:
    def __init__(self, ticker: str, score: float = 0.85, evidence: str = "good"):
        self.instrument = _FakeInstrument(ticker)
        self.score = score
        self.evidence = evidence


def test_format_equity_scan_contains_tickers():
    alerts = TelegramAlerts(token="t", chat_id="1")
    swing = [_FakeSwingCandidate("TEST", "earnings_approaching", "earnings Jun 4")]
    core = [_FakeCoreCandidate("NVDA")]
    msg = alerts.format_equity_scan(swing, core, analyst_count=1)
    assert "TEST" in msg
    assert "NVDA" in msg


def test_format_equity_scan_header():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_equity_scan([], [], analyst_count=0)
    assert "EQUITY SCAN" in msg
    assert "0 swing" in msg
    assert "0 core" in msg


def test_format_equity_scan_days_to_event():
    alerts = TelegramAlerts(token="t", chat_id="1")
    swing = [_FakeSwingCandidate("TEST", "earnings_approaching", "earnings Jun 4", days=2)]
    msg = alerts.format_equity_scan(swing, [], analyst_count=1)
    assert "in 2d" in msg


# ---------------------------------------------------------------------------
# format_equity_open tests
# ---------------------------------------------------------------------------

class _FakeRec:
    def __init__(self):
        self.instrument = _FakeInstrument("TEST", "TestCo")
        self.entry = 84.50
        self.stop_loss = 75.50
        self.take_profit = 98.00
        self.confidence = 0.78
        self.catalyst = "earnings Jun 4"
        self.thesis = "Strong ARR growth into earnings catalyst"


class _FakeFill:
    def __init__(self, shares: float = 2.3664):
        self.shares = shares


def test_format_equity_open_contains_ticker():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_equity_open(_FakeRec(), _FakeFill())
    assert "TEST" in msg
    assert "PAPER OPEN" in msg


def test_format_equity_open_contains_prices():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_equity_open(_FakeRec(), _FakeFill())
    assert "84.50" in msg
    assert "75.50" in msg
    assert "98.00" in msg


def test_format_equity_open_contains_rr():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_equity_open(_FakeRec(), _FakeFill())
    assert "R/R" in msg


def test_format_equity_open_contains_thesis():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_equity_open(_FakeRec(), _FakeFill())
    assert "Strong ARR" in msg


# ---------------------------------------------------------------------------
# format_equity_exit tests
# ---------------------------------------------------------------------------

class _FakeExitSignal:
    def __init__(self, position_id: int = 1, reason: str = "target_hit", exit_price: float = 98.20):
        self.position_id = position_id
        self.reason = reason
        self.exit_price = exit_price


def _portfolio_stats_fixture() -> dict:
    return {
        "open_count": 0, "closed_count": 1, "wins": 1, "losses": 0,
        "win_rate": 1.0, "realized_pnl": 32.14, "unrealized_pnl": 0.0,
        "open_positions": [],
    }


def test_format_equity_exit_win():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_equity_exit(
        _FakeExitSignal(reason="target_hit", exit_price=98.20),
        ticker="TEST", entry_price=84.50, shares=2.3664,
        portfolio_stats=_portfolio_stats_fixture(),
    )
    assert "TEST" in msg
    assert "WIN" in msg
    assert "TARGET HIT" in msg


def test_format_equity_exit_loss():
    alerts = TelegramAlerts(token="t", chat_id="1")
    stats = _portfolio_stats_fixture()
    stats.update(wins=0, losses=1, win_rate=0.0, realized_pnl=-20.0)
    msg = alerts.format_equity_exit(
        _FakeExitSignal(reason="stop_hit", exit_price=75.50),
        ticker="TEST", entry_price=84.50, shares=2.3664,
        portfolio_stats=stats,
    )
    assert "LOSS" in msg
    assert "STOP HIT" in msg


# ---------------------------------------------------------------------------
# format_equity_portfolio tests
# ---------------------------------------------------------------------------

def test_format_equity_portfolio_header():
    alerts = TelegramAlerts(token="t", chat_id="1")
    msg = alerts.format_equity_portfolio(_portfolio_stats_fixture())
    assert "PORTFOLIO" in msg


def test_format_equity_portfolio_shows_trade_count():
    alerts = TelegramAlerts(token="t", chat_id="1")
    stats = {
        "open_count": 0, "closed_count": 3, "wins": 2, "losses": 1,
        "win_rate": 0.667, "realized_pnl": 50.0, "unrealized_pnl": 0.0,
        "open_positions": [],
    }
    msg = alerts.format_equity_portfolio(stats)
    assert "3" in msg
    assert "2W" in msg
    assert "1L" in msg


# ---------------------------------------------------------------------------
# send tests (mock aiogram — no network)
# ---------------------------------------------------------------------------

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
