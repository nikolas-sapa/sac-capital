"""Calibration diagnostics from the equity ledger.

Answers one question before any risk escalation: does stated confidence
predict outcomes, or is it inverted? Read-only over the ledger DB.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from equities.analysis.attribution import _conf_band

_HIGH_BAND = "0.75-1.00"


def _closed(db_path: str | Path) -> list[tuple[float, float]]:
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT confidence, realized_pnl FROM positions "
            "WHERE status = 'closed' AND realized_pnl IS NOT NULL "
            "AND confidence IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
    return [(float(c), float(p)) for c, p in rows]


def brier_by_band(db_path: str | Path = "data/equity.db") -> dict[str, float]:
    """Mean (confidence - outcome)^2 per band; outcome = 1 if the trade won."""
    groups: dict[str, list[float]] = {}
    for conf, pnl in _closed(db_path):
        outcome = 1.0 if pnl > 0 else 0.0
        groups.setdefault(_conf_band(conf), []).append((conf - outcome) ** 2)
    return {band: sum(v) / len(v) for band, v in groups.items() if v}


def calibration_inverted(db_path: str | Path = "data/equity.db", min_n: int = 3) -> bool:
    """True when the top confidence band underperforms a lower band, both with n >= min_n."""
    bands: dict[str, list[float]] = {}
    for conf, pnl in _closed(db_path):
        bands.setdefault(_conf_band(conf), []).append(pnl)
    high = bands.get(_HIGH_BAND)
    if high is None or len(high) < min_n:
        return False
    high_wr = sum(1 for p in high if p > 0) / len(high)
    for band, pnls in bands.items():
        if band == _HIGH_BAND or len(pnls) < min_n:
            continue
        low_wr = sum(1 for p in pnls if p > 0) / len(pnls)
        if high_wr < low_wr:
            return True
    return False
