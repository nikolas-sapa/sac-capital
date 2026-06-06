"""07e — Forward-paper trade tracker for the kill-gate.

Records every paper trade entry and exit with full cost accounting.
Provides the data the KillGate reads to evaluate whether the strategy
has cleared the evidence bar for real-capital promotion.
"""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from equities.killgate.cost_model import net_pnl

_CREATE = """
CREATE TABLE IF NOT EXISTS forward_paper (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT    NOT NULL,
    sleeve       TEXT    NOT NULL,
    entry_price  REAL    NOT NULL,
    exit_price   REAL,
    shares       REAL    NOT NULL,
    is_gap_stop  INTEGER NOT NULL DEFAULT 0,
    net_pnl      REAL,
    status       TEXT    NOT NULL DEFAULT 'open',
    opened_at    TEXT    NOT NULL,
    closed_at    TEXT,
    strategy     TEXT    NOT NULL DEFAULT ''
)
"""


@dataclass(frozen=True)
class ForwardPaperTrade:
    id: int
    ticker: str
    sleeve: str
    entry_price: float
    exit_price: float | None
    shares: float
    is_gap_stop: bool
    net_pnl: float | None
    status: str   # "open" | "closed"
    opened_at: str
    closed_at: str | None
    strategy: str


class ForwardPaperTracker:
    """SQLite-backed tracker for forward-paper trades used by the kill-gate."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._path))
        self._con.row_factory = sqlite3.Row
        self._con.execute(_CREATE)
        self._con.commit()

    def record_entry(
        self,
        ticker: str,
        sleeve: str,
        entry_price: float,
        shares: float,
        strategy: str = "",
    ) -> int:
        now = datetime.now(tz=timezone.utc).isoformat()
        cur = self._con.execute(
            "INSERT INTO forward_paper (ticker, sleeve, entry_price, shares, opened_at, strategy)"
            " VALUES (?,?,?,?,?,?)",
            (ticker, sleeve, entry_price, shares, now, strategy),
        )
        self._con.commit()
        return int(cur.lastrowid)

    def record_exit(
        self,
        trade_id: int,
        exit_price: float,
        is_gap_stop: bool = False,
    ) -> None:
        row = self._con.execute(
            "SELECT entry_price, shares FROM forward_paper WHERE id=?", (trade_id,)
        ).fetchone()
        if row is None:
            return
        pnl = net_pnl(
            entry_price=row["entry_price"],
            exit_price=exit_price,
            shares=row["shares"],
            is_gap_stop=is_gap_stop,
        )
        now = datetime.now(tz=timezone.utc).isoformat()
        self._con.execute(
            "UPDATE forward_paper SET exit_price=?, is_gap_stop=?, net_pnl=?, "
            "status='closed', closed_at=? WHERE id=?",
            (exit_price, int(is_gap_stop), pnl, now, trade_id),
        )
        self._con.commit()

    def record_exit_for_open_trade(
        self,
        ticker: str,
        exit_price: float,
        *,
        sleeve: str | None = None,
        strategy: str | None = None,
        is_gap_stop: bool = False,
    ) -> bool:
        """Close the oldest matching open forward-paper trade.

        The equity ledger owns position ids, while this tracker owns its own ids.
        Runner exits therefore reconcile by ticker/sleeve/strategy.
        """
        clauses = ["ticker=?", "status='open'"]
        params: list[Any] = [ticker]
        if sleeve is not None:
            clauses.append("sleeve=?")
            params.append(sleeve)
        if strategy is not None:
            clauses.append("strategy=?")
            params.append(strategy)
        row = self._con.execute(
            f"SELECT id FROM forward_paper WHERE {' AND '.join(clauses)} ORDER BY id LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            return False
        self.record_exit(row["id"], exit_price=exit_price, is_gap_stop=is_gap_stop)
        return True

    def closed_trades(self, strategy: str | None = None) -> list[ForwardPaperTrade]:
        if strategy:
            rows = self._con.execute(
                "SELECT * FROM forward_paper WHERE status='closed' AND strategy=? ORDER BY id",
                (strategy,),
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT * FROM forward_paper WHERE status='closed' ORDER BY id"
            ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def open_trades(self) -> list[ForwardPaperTrade]:
        rows = self._con.execute(
            "SELECT * FROM forward_paper WHERE status='open' ORDER BY id"
        ).fetchall()
        return [_row_to_trade(r) for r in rows]

    def close(self) -> None:
        self._con.close()


def _row_to_trade(r: sqlite3.Row) -> ForwardPaperTrade:
    return ForwardPaperTrade(
        id=r["id"],
        ticker=r["ticker"],
        sleeve=r["sleeve"],
        entry_price=r["entry_price"],
        exit_price=r["exit_price"],
        shares=r["shares"],
        is_gap_stop=bool(r["is_gap_stop"]),
        net_pnl=r["net_pnl"],
        status=r["status"],
        opened_at=r["opened_at"],
        closed_at=r["closed_at"],
        strategy=r["strategy"],
    )
