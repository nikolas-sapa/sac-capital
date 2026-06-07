"""Trade ledger: sqlite (source of truth) + CSV mirror.

Each recorded Fill becomes one row in the `fills` table. Positions are
resolved once the market settles, at which point pnl is calculated and
stored.

PnL model (binary Polymarket, share pays 1.0 if that outcome wins):
  won  = 1 if row.token_id == winning_token_id else 0
  pnl  = (shares - stake) if won else -stake

open_positions() return shape — list of dicts with at minimum:
  {
    "id":           int,
    "condition_id": str,
    "token_id":     str,
    "question":     str,
    "stake":        float,
    "shares":       float,
    "avg_price":    float,
    "fair_prob":    float,
    "confidence":   float,
    "reason":       str,
    "mode":         str,
    "timestamp":    str,   # ISO-8601
  }
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from core.execution.base import Fill

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS fills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT    NOT NULL,
    token_id     TEXT    NOT NULL,
    question     TEXT    NOT NULL,
    stake        REAL    NOT NULL,
    shares       REAL    NOT NULL,
    avg_price    REAL    NOT NULL,
    fair_prob    REAL    NOT NULL,
    confidence   REAL    NOT NULL,
    reason       TEXT    NOT NULL,
    mode         TEXT    NOT NULL,
    timestamp    TEXT    NOT NULL,
    resolved     INTEGER NOT NULL DEFAULT 0,
    won          INTEGER,          -- NULL until resolved
    pnl          REAL,             -- NULL until resolved
    strategy     TEXT    NOT NULL DEFAULT ''
)
"""

_CSV_HEADERS = [
    "id", "condition_id", "token_id", "question",
    "stake", "shares", "avg_price", "fair_prob", "confidence",
    "reason", "mode", "timestamp", "resolved", "won", "pnl", "strategy",
]


class Ledger:
    """Append-only trade ledger backed by sqlite with a CSV mirror."""

    def __init__(self, path: str | Path) -> None:
        self._db_path = Path(path)
        self._csv_path = self._db_path.with_suffix(".csv")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._db_path))
        self._con.row_factory = sqlite3.Row
        self._con.execute(_CREATE_TABLE)
        self._con.commit()
        # Auto-migration: add strategy column if it doesn't exist (old schema)
        cols = {row[1] for row in self._con.execute("PRAGMA table_info(fills)")}
        if "strategy" not in cols:
            self._con.execute(
                "ALTER TABLE fills ADD COLUMN strategy TEXT NOT NULL DEFAULT ''"
            )
            self._con.commit()
        self._ensure_csv_header()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, fill: Fill, strategy: str = "") -> None:
        """Append a fill as a new unresolved position."""
        sig = fill.signal
        market = sig.market
        row = (
            market.condition_id,
            sig.token_id,
            market.question,
            fill.stake,
            fill.shares,
            fill.avg_price,
            sig.fair_prob,
            sig.confidence,
            sig.reason,
            fill.mode,
            fill.timestamp.isoformat(),
            strategy,
        )
        cur = self._con.execute(
            """
            INSERT INTO fills
                (condition_id, token_id, question, stake, shares, avg_price,
                 fair_prob, confidence, reason, mode, timestamp, strategy)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            row,
        )
        self._con.commit()
        row_id = cur.lastrowid
        # Mirror to CSV
        full_row = self._con.execute(
            "SELECT * FROM fills WHERE id = ?", (row_id,)
        ).fetchone()
        self._append_csv(full_row)

    def resolve(self, condition_id: str, winning_token_id: str) -> int:
        """Resolve all unresolved positions for condition_id.

        Sets won/pnl/resolved on each matching row.
        Returns the number of rows updated.
        """
        rows = self._con.execute(
            "SELECT id, token_id, stake, shares FROM fills "
            "WHERE condition_id = ? AND resolved = 0",
            (condition_id,),
        ).fetchall()

        if not rows:
            return 0

        updates: list[tuple[int, float, int]] = []
        for r in rows:
            won = 1 if r["token_id"] == winning_token_id else 0
            pnl = (r["shares"] - r["stake"]) if won else -r["stake"]
            updates.append((won, pnl, r["id"]))

        self._con.executemany(
            "UPDATE fills SET resolved = 1, won = ?, pnl = ? WHERE id = ?",
            updates,
        )
        self._con.commit()
        self._rewrite_csv()
        return len(updates)

    def pnl(self) -> float:
        """Sum of realized pnl across all resolved rows (0.0 if none)."""
        result = self._con.execute(
            "SELECT COALESCE(SUM(pnl), 0.0) FROM fills WHERE resolved = 1"
        ).fetchone()[0]
        return float(result)

    def open_positions(self) -> list[dict[str, Any]]:
        """Return all unresolved positions as a list of dicts.

        Each dict exposes at minimum:
          condition_id, token_id, stake, shares
        (plus the other columns listed in the module docstring).
        """
        rows = self._con.execute(
            "SELECT id, condition_id, token_id, question, stake, shares, "
            "avg_price, fair_prob, confidence, reason, mode, timestamp, strategy "
            "FROM fills WHERE resolved = 0"
        ).fetchall()
        return [dict(r) for r in rows]

    def has_open_position(self, condition_id: str, token_id: str) -> bool:
        """Return True if this market outcome already has an unresolved fill."""
        row = self._con.execute(
            "SELECT 1 FROM fills "
            "WHERE condition_id = ? AND token_id = ? AND resolved = 0 "
            "LIMIT 1",
            (condition_id, token_id),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        """Close the underlying sqlite connection."""
        self._con.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_csv_header(self) -> None:
        if not self._csv_path.exists():
            with open(self._csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
                writer.writeheader()

    def _append_csv(self, row: sqlite3.Row) -> None:
        with open(self._csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            writer.writerow(dict(row))

    def _rewrite_csv(self) -> None:
        """Rewrite the entire CSV from sqlite so resolved/won/pnl are current."""
        rows = self._con.execute("SELECT * FROM fills ORDER BY id").fetchall()
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
