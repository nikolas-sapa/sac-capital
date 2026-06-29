from __future__ import annotations

import sqlite3

from core.bot.command_handler import CommandHandler
from core.config import Settings


def _settings() -> Settings:
    return Settings(
        execution_provider="alpaca_paper",
        alpaca_api_key_id="PK1234567890",
        alpaca_secret_key="secret-value",
        alpaca_paper=True,
        alpaca_base_url="https://paper-api.alpaca.markets",
        live_trading_enabled=False,
        bankroll_usd=1000.0,
        max_position_pct=0.02,
        research_probe_pct=0.005,
        core_dca_pct=0.01,
        max_order_usd=25.0,
        max_daily_order_count=3,
        allow_extended_hours=False,
    )


def _handler(db_path) -> CommandHandler:
    return CommandHandler(equity_db=db_path, config_loader=_settings)


def _create_positions_table(db_path) -> None:
    con = sqlite3.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE positions (
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            entry_price REAL NOT NULL,
            mark_price REAL,
            stop_loss REAL,
            take_profit REAL,
            unrealized_pnl REAL,
            realized_pnl REAL,
            status TEXT NOT NULL,
            exit_price REAL,
            exit_reason TEXT,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            thesis TEXT NOT NULL DEFAULT '',
            strategy TEXT NOT NULL DEFAULT '',
            execution_provider TEXT NOT NULL DEFAULT 'internal_paper',
            broker_order_id TEXT NOT NULL DEFAULT '',
            broker_order_status TEXT NOT NULL DEFAULT '',
            broker_filled_qty REAL NOT NULL DEFAULT 0.0,
            broker_avg_fill_price REAL
        )
        """
    )
    con.commit()
    con.close()


def test_help_lists_read_only_ops_commands(tmp_path):
    msg = _handler(tmp_path / "equity.db").dispatch("/help")

    assert "/alpaca" in msg
    assert "/orders" in msg
    assert "/risk" in msg


def test_alpaca_reports_config_without_secret(tmp_path):
    db_path = tmp_path / "equity.db"
    _create_positions_table(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO positions "
        "(ticker, shares, entry_price, mark_price, stop_loss, take_profit, unrealized_pnl, "
        "status, opened_at, strategy, execution_provider, broker_order_id, broker_order_status, "
        "broker_filled_qty, broker_avg_fill_price) "
        "VALUES ('AMAT', 0.01, 450.0, 451.0, NULL, NULL, 0.01, 'open', "
        "'2026-06-06T12:00:00', 'research', 'alpaca_paper', 'ord_123456', 'accepted', 0.0, NULL)"
    )
    con.commit()
    con.close()

    msg = _handler(db_path).dispatch("/alpaca")

    assert "Provider: alpaca_paper" in msg
    assert "Paper: yes" in msg
    assert "Key ID: ...7890" in msg
    assert "secret-value" not in msg
    assert "Ledger Alpaca open: 1" in msg


def test_orders_reports_broker_status_from_local_ledger(tmp_path):
    db_path = tmp_path / "equity.db"
    _create_positions_table(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO positions "
        "(ticker, shares, entry_price, mark_price, stop_loss, take_profit, unrealized_pnl, "
        "status, opened_at, strategy, execution_provider, broker_order_id, broker_order_status, "
        "broker_filled_qty, broker_avg_fill_price) "
        "VALUES ('LRCX', 0.02, 303.0, 303.0, NULL, NULL, 0.0, 'open', "
        "'2026-06-06T12:00:00', 'research', 'alpaca_paper', 'ord_abcdef123456', "
        "'accepted', 0.0, NULL)"
    )
    con.commit()
    con.close()

    msg = _handler(db_path).dispatch("/orders")

    assert "LRCX" in msg
    assert "accepted" in msg
    assert "alpaca_paper" in msg
    assert "Filled 0.000000 @ n/a" in msg


def test_risk_reports_local_exposure(tmp_path):
    db_path = tmp_path / "equity.db"
    _create_positions_table(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO positions "
        "(ticker, shares, entry_price, mark_price, stop_loss, take_profit, unrealized_pnl, "
        "status, opened_at, strategy) "
        "VALUES ('ENTG', 0.04, 125.0, 130.0, NULL, NULL, 0.2, 'open', "
        "'2026-06-06T12:00:00', 'research')"
    )
    con.commit()
    con.close()

    msg = _handler(db_path).dispatch("/risk")

    assert "Bankroll: $1000.00" in msg
    assert "Max order: $25.00" in msg
    assert "Open positions: 1" in msg
    assert "Gross local exposure: $5.20" in msg
    assert "Largest name: ENTG" in msg


def test_positions_handles_missing_stop_and_target(tmp_path):
    db_path = tmp_path / "equity.db"
    _create_positions_table(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO positions "
        "(ticker, shares, entry_price, mark_price, stop_loss, take_profit, unrealized_pnl, "
        "status, opened_at, strategy) "
        "VALUES ('AMAT', 0.01, 450.0, 451.0, NULL, NULL, 0.01, 'open', "
        "'2026-06-06T12:00:00', 'research')"
    )
    con.commit()
    con.close()

    msg = _handler(db_path).dispatch("/positions")

    assert "AMAT" in msg
    assert "n/a" in msg


def test_closed_reports_realized_equity_trades(tmp_path):
    db_path = tmp_path / "equity.db"
    _create_positions_table(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO positions "
        "(ticker, shares, entry_price, mark_price, stop_loss, take_profit, unrealized_pnl, "
        "realized_pnl, status, exit_price, exit_reason, opened_at, closed_at, thesis, strategy) "
        "VALUES ('AMAT', 0.01, 474.88, 668.0, NULL, NULL, 0.0, 2.13, 'closed', "
        "668.0, 'time_stop', '2026-06-06T06:10:52', '2026-06-27T06:26:05', "
        "'lagged bottleneck supplier behind AMD', 'research_static')"
    )
    con.commit()
    con.close()

    msg = _handler(db_path).dispatch("/closed")

    assert "CLOSED POSITIONS (1)" in msg
    assert "AMAT" in msg
    assert "+$2.13" in msg
    assert "+40.7%" in msg
    assert "research_static" in msg
