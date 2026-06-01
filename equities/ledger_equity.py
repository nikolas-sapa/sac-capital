from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from equities.strategy import Recommendation

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS positions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT    NOT NULL,
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
    strategy       TEXT    NOT NULL DEFAULT ''
)
"""

_CSV_HEADERS = [
    "id", "ticker", "sleeve", "side", "shares", "entry_price",
    "stop_loss", "take_profit", "mark_price", "unrealized_pnl",
    "realized_pnl", "status", "exit_price", "exit_reason",
    "confidence", "thesis", "mode", "opened_at", "closed_at", "strategy",
]


class EquityLedger:
    def __init__(self, path: str | Path) -> None:
        self._db_path = Path(path)
        self._csv_path = self._db_path.with_suffix(".csv")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._db_path))
        self._con.row_factory = sqlite3.Row
        self._con.execute(_CREATE_TABLE)
        self._con.commit()
        self._ensure_csv_header()

    def open_position(self, rec: Recommendation, shares: float, fill_price: float,
                      opened_at: datetime, mode: str, strategy: str = "") -> int:
        row = (
            rec.instrument.ticker, rec.sleeve.value, rec.side, shares, fill_price,
            rec.stop_loss, rec.take_profit, fill_price, 0.0,
            rec.confidence, rec.thesis, mode, opened_at.isoformat(), strategy,
        )
        cur = self._con.execute(
            """
            INSERT INTO positions
                (ticker, sleeve, side, shares, entry_price, stop_loss, take_profit,
                 mark_price, unrealized_pnl, confidence, thesis, mode, opened_at, strategy)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            row,
        )
        self._con.commit()
        self._rewrite_csv()
        return int(cur.lastrowid)

    def open_positions(self) -> list[dict[str, Any]]:
        rows = self._con.execute(
            "SELECT * FROM positions WHERE status = 'open'"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark(self, ticker: str, price: float) -> int:
        rows = self._con.execute(
            "SELECT id, shares, entry_price FROM positions "
            "WHERE ticker = ? AND status = 'open'",
            (ticker,),
        ).fetchall()
        updates = [
            (price, (price - r["entry_price"]) * r["shares"], r["id"])
            for r in rows
        ]
        self._con.executemany(
            "UPDATE positions SET mark_price = ?, unrealized_pnl = ? WHERE id = ?",
            updates,
        )
        self._con.commit()
        self._rewrite_csv()
        return len(updates)

    def close_position(self, position_id: int, exit_price: float,
                       exit_reason: str, closed_at: datetime) -> None:
        row = self._con.execute(
            "SELECT shares, entry_price FROM positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        realized = (exit_price - row["entry_price"]) * row["shares"]
        self._con.execute(
            "UPDATE positions SET status='closed', exit_price=?, exit_reason=?, "
            "realized_pnl=?, mark_price=?, unrealized_pnl=0.0, closed_at=? WHERE id=?",
            (exit_price, exit_reason, realized, exit_price, closed_at.isoformat(), position_id),
        )
        self._con.commit()
        self._rewrite_csv()

    def realized_pnl(self) -> float:
        result = self._con.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0.0) FROM positions WHERE status = 'closed'"
        ).fetchone()[0]
        return float(result)

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

    def _rewrite_csv(self) -> None:
        rows = self._con.execute("SELECT * FROM positions ORDER BY id").fetchall()
        with open(self._csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            w.writeheader()
            for row in rows:
                w.writerow(dict(row))
