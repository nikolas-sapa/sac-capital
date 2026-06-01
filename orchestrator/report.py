from __future__ import annotations

from datetime import date

from core.ledger import Ledger
from orchestrator.performance import StrategyStats


def daily_report(ledger: Ledger) -> str:
    """Return a formatted per-strategy + portfolio summary string."""
    rows = ledger._con.execute(
        "SELECT DISTINCT strategy FROM fills WHERE strategy != ''"
    ).fetchall()
    strategy_names = [r["strategy"] for r in rows]

    stats_engine = StrategyStats(ledger)
    lines = [f"Daily Report — {date.today().isoformat()}\n"]

    for name in sorted(strategy_names):
        s = stats_engine.rolling(name, window=100)
        lines.append(f"  [{name}]")
        lines.append(f"    resolved: {s.n_resolved}")
        lines.append(f"    win_rate: {s.win_rate:.1%}")
        lines.append(f"    roi:      {s.roi:+.2%}")
        lines.append(f"    brier:    {s.brier_score:.4f}")
        lines.append(f"    score:    {s.expectancy:.4f}")

    open_pos = ledger.open_positions()
    open_exposure = sum(p["stake"] for p in open_pos)

    result = ledger._con.execute(
        "SELECT COALESCE(SUM(pnl), 0.0), COALESCE(SUM(stake), 0.0) FROM fills WHERE resolved = 1"
    ).fetchone()
    total_pnl = float(result[0])
    total_stake = float(result[1])
    total_roi = total_pnl / total_stake if total_stake > 0 else 0.0

    lines.append("\n  [PORTFOLIO]")
    lines.append(f"    total_pnl:      {total_pnl:+.2f}")
    lines.append(f"    total_roi:      {total_roi:+.2%}")
    lines.append(f"    open_positions: {len(open_pos)}")
    lines.append(f"    open_exposure:  {open_exposure:.2f}")

    return "\n".join(lines)
