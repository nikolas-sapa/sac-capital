from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from equities.strategy import Recommendation

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS positions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT    NOT NULL,
    sector         TEXT    NOT NULL DEFAULT '',
    sleeve         TEXT    NOT NULL,
    side           TEXT    NOT NULL,
    shares         REAL    NOT NULL,
    entry_price    REAL    NOT NULL,
    stop_loss      REAL,
    take_profit    REAL,
    mark_price     REAL,
    unrealized_pnl REAL,
    realized_pnl   REAL,
    status         TEXT    NOT NULL DEFAULT 'open',
    exit_price     REAL,
    exit_reason    TEXT,
    confidence     REAL    NOT NULL,
    thesis         TEXT    NOT NULL,
    mode           TEXT    NOT NULL,
    opened_at      TEXT    NOT NULL,
    closed_at      TEXT,
    strategy       TEXT    NOT NULL DEFAULT '',
    execution_provider TEXT NOT NULL DEFAULT 'internal_paper',
    broker_order_id    TEXT NOT NULL DEFAULT '',
    broker_client_order_id TEXT NOT NULL DEFAULT '',
    broker_order_status TEXT NOT NULL DEFAULT '',
    broker_filled_qty REAL NOT NULL DEFAULT 0.0,
    broker_avg_fill_price REAL,
    broker_submitted_at TEXT NOT NULL DEFAULT '',
    broker_filled_at TEXT NOT NULL DEFAULT '',
    broker_canceled_at TEXT NOT NULL DEFAULT '',
    broker_raw_json TEXT NOT NULL DEFAULT '',
    analysis_json  TEXT NOT NULL DEFAULT '{}'
)
"""

_CSV_HEADERS = [
    "id", "ticker", "sector", "sleeve", "side", "shares", "entry_price",
    "stop_loss", "take_profit", "mark_price", "unrealized_pnl",
    "realized_pnl", "status", "exit_price", "exit_reason",
    "confidence", "thesis", "mode", "opened_at", "closed_at", "strategy",
    "execution_provider", "broker_order_id", "broker_order_status",
    "broker_client_order_id", "broker_filled_qty", "broker_avg_fill_price",
    "broker_submitted_at", "broker_filled_at", "broker_canceled_at", "broker_raw_json",
    "analysis_json", "signal_class",
]

_BROKER_COLUMNS = {
    "sector": "TEXT NOT NULL DEFAULT ''",
    "execution_provider": "TEXT NOT NULL DEFAULT 'internal_paper'",
    "broker_order_id": "TEXT NOT NULL DEFAULT ''",
    "broker_client_order_id": "TEXT NOT NULL DEFAULT ''",
    "broker_order_status": "TEXT NOT NULL DEFAULT ''",
    "broker_filled_qty": "REAL NOT NULL DEFAULT 0.0",
    "broker_avg_fill_price": "REAL",
    "broker_submitted_at": "TEXT NOT NULL DEFAULT ''",
    "broker_filled_at": "TEXT NOT NULL DEFAULT ''",
    "broker_canceled_at": "TEXT NOT NULL DEFAULT ''",
    "broker_raw_json": "TEXT NOT NULL DEFAULT ''",
    "analysis_json": "TEXT NOT NULL DEFAULT '{}'",
    "signal_class": "TEXT NOT NULL DEFAULT ''",
}


class EquityLedger:
    def __init__(self, path: str | Path) -> None:
        self._db_path = Path(path)
        self._csv_path = self._db_path.with_suffix(".csv")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._db_path))
        self._con.row_factory = sqlite3.Row
        self._con.execute(_CREATE_TABLE)
        for name, ddl in _BROKER_COLUMNS.items():
            self._ensure_column(name, ddl)
        self._ensure_column("high_water_price", "REAL")
        self._con.commit()
        self._ensure_csv_header()

    def open_position(self, rec: Recommendation, shares: float, fill_price: float,
                      opened_at: datetime, mode: str, strategy: str = "",
                      execution_provider: str = "internal_paper",
                      broker_order_id: str = "",
                      broker_client_order_id: str = "",
                      broker_order_status: str = "",
                      sector: str = "",
                      status: str = "open",
                      signal_class: str = "") -> int:
        analysis_json = json.dumps(
            {**(rec.analysis or {}), "horizon": rec.horizon}, ensure_ascii=False
        )
        row = (
            rec.instrument.ticker, sector, rec.sleeve.value, rec.side, shares, fill_price,
            rec.stop_loss, rec.take_profit, fill_price, 0.0,
            status, rec.confidence, rec.thesis, mode, opened_at.isoformat(), strategy,
            execution_provider, broker_order_id, broker_client_order_id, broker_order_status,
            analysis_json, signal_class,
        )
        cur = self._con.execute(
            """
            INSERT INTO positions
                (ticker, sector, sleeve, side, shares, entry_price, stop_loss, take_profit,
                 mark_price, unrealized_pnl, status, confidence, thesis, mode, opened_at, strategy,
                 execution_provider, broker_order_id, broker_client_order_id, broker_order_status,
                 analysis_json, signal_class)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            row,
        )
        self._con.commit()
        self._rewrite_csv()
        return int(cur.lastrowid)

    def open_positions(self) -> list[dict[str, Any]]:
        rows = self._con.execute(
            "SELECT * FROM positions WHERE status IN ('open', 'submitted', 'partially_filled')"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark(self, ticker: str, price: float) -> int:
        rows = self._con.execute(
            "SELECT id, shares, entry_price FROM positions "
            "WHERE ticker = ? AND status IN ('open', 'partially_filled')",
            (ticker,),
        ).fetchall()
        updates = [
            (price, (price - r["entry_price"]) * r["shares"], price, r["id"])
            for r in rows
        ]
        self._con.executemany(
            "UPDATE positions SET mark_price = ?, unrealized_pnl = ?, "
            "high_water_price = MAX(COALESCE(high_water_price, entry_price), ?) "
            "WHERE id = ?",
            updates,
        )
        self._con.commit()
        self._rewrite_csv()
        return len(updates)

    def update_analysis_field(self, position_id: int, key: str, value) -> None:
        row = self._con.execute(
            "SELECT analysis_json FROM positions WHERE id = ?", (position_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Position {position_id} not found")
        data = json.loads(row["analysis_json"] or "{}")
        data[key] = value
        self._con.execute(
            "UPDATE positions SET analysis_json = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), position_id),
        )
        self._con.commit()
        self._rewrite_csv()

    def update_broker_order(
        self,
        position_id: int,
        *,
        execution_provider: str | None = None,
        broker_order_id: str | None = None,
        broker_client_order_id: str | None = None,
        broker_order_status: str | None = None,
        broker_filled_qty: float | None = None,
        broker_avg_fill_price: float | None = None,
        status: str | None = None,
        entry_price: float | None = None,
        shares: float | None = None,
        broker_submitted_at: str | None = None,
        broker_filled_at: str | None = None,
        broker_canceled_at: str | None = None,
        broker_raw_json: str | None = None,
    ) -> None:
        updates: dict[str, Any] = {
            "execution_provider": execution_provider,
            "broker_order_id": broker_order_id,
            "broker_client_order_id": broker_client_order_id,
            "broker_order_status": broker_order_status,
            "broker_filled_qty": broker_filled_qty,
            "broker_avg_fill_price": broker_avg_fill_price,
            "status": status,
            "entry_price": entry_price,
            "mark_price": entry_price,
            "shares": shares,
            "broker_submitted_at": broker_submitted_at,
            "broker_filled_at": broker_filled_at,
            "broker_canceled_at": broker_canceled_at,
            "broker_raw_json": broker_raw_json,
        }
        assignments = [f"{name}=?" for name, value in updates.items() if value is not None]
        values = [value for value in updates.values() if value is not None]
        if not assignments:
            return
        values.append(position_id)
        self._con.execute(
            f"UPDATE positions SET {', '.join(assignments)} WHERE id=?",
            values,
        )
        self._con.commit()
        self._rewrite_csv()

    def position_by_broker_order_id(self, broker_order_id: str) -> dict[str, Any] | None:
        row = self._con.execute(
            "SELECT * FROM positions WHERE broker_order_id=?",
            (broker_order_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def position_by_broker_client_order_id(self, broker_client_order_id: str) -> dict[str, Any] | None:
        row = self._con.execute(
            "SELECT * FROM positions WHERE broker_client_order_id=?",
            (broker_client_order_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def broker_orders_opened_on(self, day_iso: str, provider: str = "alpaca_paper") -> int:
        row = self._con.execute(
            "SELECT COUNT(*) FROM positions "
            "WHERE execution_provider=? "
            "AND (broker_order_id <> '' OR broker_client_order_id <> '') "
            "AND status NOT IN ('void','rejected') "
            "AND substr(opened_at, 1, 10)=?",
            (provider, day_iso),
        ).fetchone()
        return int(row[0] or 0)

    def close_position(self, position_id: int, exit_price: float,
                       exit_reason: str, closed_at: datetime) -> None:
        row = self._con.execute(
            "SELECT shares, entry_price FROM positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Position {position_id} not found")
        if row["entry_price"] is None or row["shares"] is None:
            raise ValueError(f"Position {position_id} missing entry_price or shares")
        realized = (exit_price - row["entry_price"]) * row["shares"]
        self._con.execute(
            "UPDATE positions SET status='closed', exit_price=?, exit_reason=?, "
            "realized_pnl=?, mark_price=?, unrealized_pnl=0.0, closed_at=? WHERE id=?",
            (exit_price, exit_reason, realized, exit_price, closed_at.isoformat(), position_id),
        )
        self._con.commit()
        self._rewrite_csv()

    def void_position(
        self,
        position_id: int,
        reason: str,
        closed_at: datetime,
        status: str = "void",
    ) -> None:
        self._con.execute(
            "UPDATE positions SET status=?, exit_reason=?, realized_pnl=0.0, "
            "unrealized_pnl=0.0, closed_at=? WHERE id=?",
            (status, reason, closed_at.isoformat(), position_id),
        )
        self._con.commit()
        self._rewrite_csv()

    def realized_pnl(self) -> float:
        result = self._con.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0.0) FROM positions WHERE status = 'closed'"
        ).fetchone()[0]
        return float(result)

    def realized_pnl_on(self, day_iso: str) -> float:
        result = self._con.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0.0) FROM positions "
            "WHERE status = 'closed' AND substr(closed_at, 1, 10)=?",
            (day_iso,),
        ).fetchone()[0]
        return float(result)

    def portfolio_stats(self) -> dict[str, Any]:
        closed = self._con.execute(
            "SELECT realized_pnl FROM positions WHERE status = 'closed'"
        ).fetchall()
        open_rows = self._con.execute(
            "SELECT ticker, entry_price, mark_price, unrealized_pnl "
            "FROM positions WHERE status IN ('open', 'partially_filled')"
        ).fetchall()
        total = len(closed)
        wins = sum(1 for r in closed if r["realized_pnl"] > 0)
        return {
            "open_count": len(open_rows),
            "closed_count": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": wins / total if total > 0 else 0.0,
            "realized_pnl": sum(r["realized_pnl"] for r in closed),
            "unrealized_pnl": sum((r["unrealized_pnl"] or 0.0) for r in open_rows),
            "open_positions": [dict(r) for r in open_rows],
        }

    def pending_notional(self) -> float:
        # ponytail: reserves fully-unfilled orders only; the unfilled remainder of a
        # partially_filled order is not reserved — add remainder tracking if partial
        # fills become common at this order size.
        row = self._con.execute(
            "SELECT COALESCE(SUM(shares * entry_price), 0.0) FROM positions "
            "WHERE status = 'submitted'"
        ).fetchone()[0]
        return float(row)

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "EquityLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_csv_header(self) -> None:
        if not self._csv_path.exists():
            with open(self._csv_path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=_CSV_HEADERS).writeheader()

    def _ensure_column(self, name: str, ddl: str) -> None:
        existing = {
            row["name"] for row in self._con.execute("PRAGMA table_info(positions)").fetchall()
        }
        if name not in existing:
            self._con.execute(f"ALTER TABLE positions ADD COLUMN {name} {ddl}")

    def _rewrite_csv(self) -> None:
        rows = self._con.execute("SELECT * FROM positions ORDER BY id").fetchall()
        tmp = self._csv_path.with_suffix(self._csv_path.suffix + ".tmp")
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            w.writeheader()
            for row in rows:
                d = dict(row)
                w.writerow({k: d.get(k, "") for k in _CSV_HEADERS})
        tmp.replace(self._csv_path)  # atomic on POSIX
