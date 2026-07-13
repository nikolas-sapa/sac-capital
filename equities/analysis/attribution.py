"""Outcome attribution — grade past reasoning by realized PnL.

Reads closed positions from the equity ledger and buckets realized outcomes by
the reasoning dimensions recorded on each decision (confidence band, strategy,
sector, exit reason). Surfaces which patterns actually pay, so the analyst can
be told where its own conviction has been miscalibrated.

Read-only over the ledger DB — never writes, never touches the broker.

ponytail: buckets only over columns already on the positions row (no join to
mantle_commitments.jsonl). Add a catalyst/event_type dimension by joining the
commitment log if single-table calibration proves too coarse.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_CONF_BANDS = ((0.0, 0.6), (0.6, 0.75), (0.75, 1.0001))


@dataclass(frozen=True)
class Bucket:
    dimension: str  # "confidence" | "strategy" | "sector" | "exit_reason"
    label: str
    n: int
    wins: int
    avg_pnl: float
    total_pnl: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0


@dataclass(frozen=True)
class AttributionReport:
    closed_trades: int
    total_realized_pnl: float
    overall_win_rate: float
    buckets: list[Bucket]


def _conf_band(conf: float) -> str:
    for lo, hi in _CONF_BANDS:
        if lo <= conf < hi:
            return f"{lo:.2f}-{min(hi, 1.0):.2f}"
    return "unknown"


def _closed_rows(db_path: str | Path) -> list[dict]:
    """Closed positions with a realized outcome. Empty list if table absent."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT confidence, strategy, sector, exit_reason, realized_pnl "
            "FROM positions WHERE status = 'closed' AND realized_pnl IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
    return [dict(r) for r in rows]


def _bucketize(rows: list[dict], dimension: str, key) -> list[Bucket]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        label = key(row)
        if not label:
            continue
        groups.setdefault(str(label), []).append(float(row["realized_pnl"]))
    out = []
    for label, pnls in groups.items():
        wins = sum(1 for p in pnls if p > 0)
        out.append(
            Bucket(
                dimension=dimension,
                label=label,
                n=len(pnls),
                wins=wins,
                avg_pnl=sum(pnls) / len(pnls),
                total_pnl=sum(pnls),
            )
        )
    return out


def attribute(db_path: str | Path = "data/equity.db") -> AttributionReport:
    rows = _closed_rows(db_path)
    total = sum(float(r["realized_pnl"]) for r in rows)
    wins = sum(1 for r in rows if float(r["realized_pnl"]) > 0)
    buckets: list[Bucket] = []
    buckets += _bucketize(rows, "confidence", lambda r: _conf_band(float(r["confidence"])))
    buckets += _bucketize(rows, "strategy", lambda r: r["strategy"])
    buckets += _bucketize(rows, "sector", lambda r: r["sector"])
    buckets += _bucketize(rows, "exit_reason", lambda r: r["exit_reason"])
    # Rank worst total PnL first — the buckets bleeding money are what to fix.
    buckets.sort(key=lambda b: b.total_pnl)
    return AttributionReport(
        closed_trades=len(rows),
        total_realized_pnl=total,
        overall_win_rate=wins / len(rows) if rows else 0.0,
        buckets=buckets,
    )


def graded_lessons(report: AttributionReport, min_n: int = 3) -> list[str]:
    """Directive lesson lines for buckets that deviate from the book average.

    Only buckets with at least `min_n` trades — small samples are noise, not
    signal. Emitted worst-first so the model reads its costliest bias up top.
    """
    if report.closed_trades < min_n:
        return []
    base = report.overall_win_rate
    lessons = []
    for b in report.buckets:
        if b.n < min_n:
            continue
        under = b.avg_pnl < 0 and b.win_rate <= base
        over = b.avg_pnl > 0 and b.win_rate >= base
        if not (under or over):
            continue
        verdict = "underperforms — discount these" if under else "outperforms — favor these"
        lessons.append(
            f"{b.dimension}={b.label}: {b.wins}/{b.n} wins, "
            f"avg {b.avg_pnl:+.2f} (total {b.total_pnl:+.2f}) — {verdict}."
        )
    return lessons


def format_report(report: AttributionReport) -> str:
    if not report.closed_trades:
        return "No closed trades with realized PnL yet — nothing to attribute."
    lines = [
        f"Closed trades: {report.closed_trades} | "
        f"realized PnL: {report.total_realized_pnl:+.2f} | "
        f"win rate: {report.overall_win_rate:.0%}",
        "",
        f"{'dimension':<12} {'bucket':<22} {'n':>3} {'win%':>5} {'avg':>8} {'total':>9}",
    ]
    for b in report.buckets:
        lines.append(
            f"{b.dimension:<12} {b.label:<22} {b.n:>3} "
            f"{b.win_rate:>4.0%} {b.avg_pnl:>+8.2f} {b.total_pnl:>+9.2f}"
        )
    lessons = graded_lessons(report)
    if lessons:
        lines += ["", "Graded lessons (min 3 trades):"]
        lines += [f"  - {line}" for line in lessons]
    return "\n".join(lines)
