"""Signal statistics tracking — regime-conditional win-rate memory for recommendations.

Rebuilds signal_stats table from closed positions and provides formatted lines
for prompt injection into the analyst.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def update_signal_stats(ledger, regime: str, window_days: int = 30) -> None:
    """Rebuild signal_stats table from closed positions in the window.

    Groups closed positions by signal_class, filters by realized trades in the
    last window_days, and computes win rates for each class in the given regime.

    Args:
        ledger: EquityLedger instance with _con connection
        regime: Regime label (e.g. "high_vol" or "low_vol")
        window_days: Look-back window in days (default 30)
    """
    # Ensure signal_stats table exists
    ledger._ensure_column("signal_class", "TEXT NOT NULL DEFAULT ''")
    ledger._con.execute("""
        CREATE TABLE IF NOT EXISTS signal_stats (
            signal_class TEXT NOT NULL,
            regime TEXT NOT NULL,
            window_end TEXT NOT NULL,
            trades INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            PRIMARY KEY (signal_class, regime)
        )
    """)

    # Calculate window start (now - window_days)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=window_days)
    cutoff_iso = cutoff.isoformat()

    # Query closed positions in window, grouped by signal_class
    # Win = realized_pnl > 0, Loss = realized_pnl <= 0
    rows = ledger._con.execute("""
        SELECT
            signal_class,
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM positions
        WHERE status = 'closed'
          AND closed_at IS NOT NULL
          AND closed_at > ?
          AND signal_class != ''
        GROUP BY signal_class
    """, (cutoff_iso,)).fetchall()

    # Clear existing entries for this regime and rebuild
    ledger._con.execute(
        "DELETE FROM signal_stats WHERE regime = ?",
        (regime,)
    )

    # Insert computed stats
    window_end = datetime.now(tz=timezone.utc).isoformat()
    for row in rows:
        signal_class, total_trades, wins = row
        wins = wins or 0  # Handle NULL from SUM when no rows match
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        ledger._con.execute("""
            INSERT INTO signal_stats (signal_class, regime, window_end, trades, win_rate)
            VALUES (?, ?, ?, ?, ?)
        """, (signal_class, regime, window_end, total_trades, win_rate))

    ledger._con.commit()


def signal_stats_line(
    ledger,
    signal_class: str,
    regime: str,
    min_trades: int = 10,
) -> str | None:
    """Fetch and format win-rate line for prompt injection.

    Returns None if:
      - No data exists for this signal_class/regime pair
      - Trades < min_trades (cold start / insufficient sample)

    Args:
        ledger: EquityLedger instance
        signal_class: Signal origin (e.g. "earnings_approaching", "material_filing")
        regime: Regime label (e.g. "high_vol", "low_vol")
        min_trades: Minimum trades to return a line (default 10)

    Returns:
        Formatted line like "Historical 30d win rate for {signal_class} in {regime}: {win_rate:.0%} over {trades} trades — weight conviction accordingly."
        or None if insufficient data.
    """
    row = ledger._con.execute("""
        SELECT trades, win_rate
        FROM signal_stats
        WHERE signal_class = ? AND regime = ?
    """, (signal_class, regime)).fetchone()

    if row is None or row[0] < min_trades:
        return None

    trades, win_rate = row
    return (
        f"Historical 30d win rate for {signal_class} in {regime}: "
        f"{win_rate:.0%} over {trades} trades — weight conviction accordingly."
    )
