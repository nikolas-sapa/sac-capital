from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.ledger import Ledger

_CREATE = """
CREATE TABLE IF NOT EXISTS params (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy  TEXT    NOT NULL,
    key       TEXT    NOT NULL,
    value     TEXT    NOT NULL,
    reason    TEXT    NOT NULL DEFAULT '',
    evidence  TEXT    NOT NULL DEFAULT '',
    timestamp TEXT    NOT NULL,
    active    INTEGER NOT NULL DEFAULT 1
)
"""


class ParamStore:
    """Versioned parameter store. Every set() snapshots the prior value.

    Values are JSON-serialized so any JSON-compatible type is supported.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._path))
        self._con.row_factory = sqlite3.Row
        self._con.execute(_CREATE)
        self._con.commit()

    def get(self, strategy: str, key: str) -> Any | None:
        """Return the current active value, or None if not set."""
        row = self._con.execute(
            "SELECT value FROM params WHERE strategy=? AND key=? AND active=1 ORDER BY id DESC LIMIT 1",
            (strategy, key),
        ).fetchone()
        return json.loads(row["value"]) if row else None

    def set(
        self,
        strategy: str,
        key: str,
        value: Any,
        reason: str = "",
        evidence: str = "",
    ) -> None:
        """Set a new value, deactivating the previous version."""
        self._con.execute(
            "UPDATE params SET active=0 WHERE strategy=? AND key=? AND active=1",
            (strategy, key),
        )
        self._con.execute(
            "INSERT INTO params (strategy, key, value, reason, evidence, timestamp) VALUES (?,?,?,?,?,?)",
            (
                strategy,
                key,
                json.dumps(value),
                reason,
                evidence,
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )
        self._con.commit()

    def history(self, strategy: str, key: str) -> list[dict]:
        """Return all versions for (strategy, key), newest first."""
        rows = self._con.execute(
            "SELECT id, value, reason, evidence, timestamp, active FROM params "
            "WHERE strategy=? AND key=? ORDER BY id DESC",
            (strategy, key),
        ).fetchall()
        return [dict(r) for r in rows]

    def rollback(self, strategy: str, key: str) -> bool:
        """Restore the previous version. Returns True if a rollback occurred."""
        rows = self._con.execute(
            "SELECT id FROM params WHERE strategy=? AND key=? ORDER BY id DESC LIMIT 2",
            (strategy, key),
        ).fetchall()
        if len(rows) < 2:
            return False
        current_id = rows[0]["id"]
        prev_id = rows[1]["id"]
        self._con.execute("UPDATE params SET active=0 WHERE id=?", (current_id,))
        self._con.execute("UPDATE params SET active=1 WHERE id=?", (prev_id,))
        self._con.commit()
        return True

    def close(self) -> None:
        self._con.close()


class RollbackGuard:
    """Reverts a parameter if post-change performance degrades past a threshold."""

    def __init__(
        self,
        store: ParamStore,
        ledger: Ledger,
        threshold: float = 0.10,
    ) -> None:
        self._store = store
        self._ledger = ledger
        self._threshold = threshold

    def check_and_rollback(
        self, strategy: str, key: str, window: int = 30
    ) -> bool:
        """Return True if a rollback was triggered."""
        history = self._store.history(strategy, key)
        if len(history) < 2:
            return False

        change_ts = history[0]["timestamp"]

        pre_rows = self._ledger._con.execute(
            """SELECT pnl, stake FROM fills
               WHERE strategy=? AND resolved=1 AND timestamp < ?
               ORDER BY timestamp DESC LIMIT ?""",
            (strategy, change_ts, window),
        ).fetchall()

        post_rows = self._ledger._con.execute(
            """SELECT pnl, stake FROM fills
               WHERE strategy=? AND resolved=1 AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (strategy, change_ts, window),
        ).fetchall()

        if not pre_rows or not post_rows:
            return False

        def _roi(rows: list) -> float:
            stake = sum(r["stake"] for r in rows)
            return sum(r["pnl"] for r in rows) / stake if stake > 0 else 0.0

        if _roi(post_rows) < _roi(pre_rows) - self._threshold:
            self._store.rollback(strategy, key)
            return True
        return False
