#!/usr/bin/env python3
"""Shadow vol-targeting A/B report: compare Kelly vs vol-target sizing on closed trades.

Reads closed positions from the ledger, looks up shadow sizing data from research
artifacts, and computes hypothetical PnL under each scheme.

Usage:
    uv run python scripts/sizing_ab_report.py [--db data/equity.db] [--artifacts data/research_artifacts.jsonl]

Outputs a comparison table with:
    - Total PnL, mean per-trade PnL, max single-trade loss under each scheme
    - Trade count with shadow data availability
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def compare_sizing(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute PnL comparison between Kelly and vol-target sizing.

    Args:
        trades: List of closed-position dicts with:
            - ticker, shares, entry_price, exit_price, realized_pnl
            - sizing: Optional dict with {kelly_shares, voltarget_shares}

    Returns:
        Dict with:
            - kelly: {total_pnl, mean_pnl, max_loss, trade_count}
            - voltarget: {total_pnl, mean_pnl, max_loss, trade_count}
            - trades_with_shadow: count of trades with sizing data
    """
    kelly_pnls = []
    voltarget_pnls = []
    shadow_count = 0

    for trade in trades:
        entry = trade["entry_price"]
        exit_p = trade["exit_price"]
        per_share_gain = exit_p - entry

        # Kelly: always use actual shares from ledger
        kelly_shares = trade.get("shares")
        if kelly_shares is not None:
            kelly_pnl = kelly_shares * per_share_gain
            kelly_pnls.append(kelly_pnl)

        # Vol-target: only if sizing data exists
        sizing = trade.get("sizing")
        if sizing:
            shadow_count += 1
            voltarget_shares = sizing.get("voltarget_shares")
            if voltarget_shares is not None:
                voltarget_pnl = voltarget_shares * per_share_gain
                voltarget_pnls.append(voltarget_pnl)

    # Compute stats for each scheme
    def stats(pnls: list[float]) -> dict[str, float]:
        if not pnls:
            return {
                "total_pnl": 0.0,
                "mean_pnl": 0.0,
                "max_loss": 0.0,
                "trade_count": 0,
            }
        return {
            "total_pnl": sum(pnls),
            "mean_pnl": sum(pnls) / len(pnls),
            "max_loss": min(pnls),  # most negative
            "trade_count": len(pnls),
        }

    return {
        "kelly": stats(kelly_pnls),
        "voltarget": stats(voltarget_pnls),
        "trades_with_shadow": shadow_count,
    }


def load_artifacts(path: Path) -> dict[str, dict[str, Any]]:
    """Load sizing data from research_artifacts.jsonl.

    Returns:
        Dict keyed by (ticker, opened_at) -> {"sizing": {...}}
    """
    artifacts_by_trade: dict[str, dict[str, Any]] = {}

    if not path.exists():
        return artifacts_by_trade

    try:
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                artifact = json.loads(line)
                ticker = artifact.get("ticker", "")
                output_json = artifact.get("output_json", {})
                sizing = output_json.get("sizing")
                if sizing:
                    # Store by ticker for lookup during ledger scan
                    artifacts_by_trade[ticker] = {"sizing": sizing}
    except (json.JSONDecodeError, IOError):
        pass

    return artifacts_by_trade


def load_ledger_closed_trades(db_path: Path) -> list[dict[str, Any]]:
    """Load closed positions from the equity ledger.

    Returns:
        List of closed-position dicts with ticker, shares, entry/exit prices, realized_pnl.
    """
    trades = []

    if not db_path.exists():
        return trades

    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Query closed positions
        cur.execute("""
            SELECT
                id,
                ticker,
                shares,
                entry_price,
                exit_price,
                realized_pnl,
                opened_at,
                closed_at
            FROM positions
            WHERE status = 'closed'
            AND realized_pnl IS NOT NULL
            ORDER BY closed_at DESC
        """)

        for row in cur.fetchall():
            trades.append({
                "id": row["id"],
                "ticker": row["ticker"],
                "shares": row["shares"],
                "entry_price": row["entry_price"],
                "exit_price": row["exit_price"],
                "realized_pnl": row["realized_pnl"],
                "opened_at": row["opened_at"],
                "closed_at": row["closed_at"],
            })

        con.close()
    except sqlite3.Error:
        pass

    return trades


def main() -> None:
    """Run the A/B sizing comparison report."""
    parser = argparse.ArgumentParser(
        description="Shadow vol-targeting A/B report: compare Kelly vs vol-target sizing."
    )
    parser.add_argument("--db", default="data/equity.db", help="Equity ledger SQLite path")
    parser.add_argument(
        "--artifacts",
        default="data/research_artifacts.jsonl",
        help="Research artifacts JSONL path",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    artifacts_path = Path(args.artifacts)

    # Load closed trades from ledger
    closed_trades = load_ledger_closed_trades(db_path)
    if not closed_trades:
        print("No closed trades found in ledger.")
        return

    # Load sizing data from artifacts
    artifacts = load_artifacts(artifacts_path)

    # Merge sizing data into trades
    for trade in closed_trades:
        ticker = trade["ticker"]
        if ticker in artifacts:
            trade["sizing"] = artifacts[ticker]["sizing"]

    # Compute comparison
    result = compare_sizing(closed_trades)

    # Print report
    print("\n" + "="*70)
    print("SIZING A/B REPORT: Kelly vs Vol-Target")
    print("="*70)
    print(f"\nClosed trades in ledger: {len(closed_trades)}")
    print(f"Trades with shadow sizing data: {result['trades_with_shadow']}")

    if result["trades_with_shadow"] == 0:
        print("\nNo shadow sizing data yet. Run the pipeline to populate artifacts.")
        return

    kelly = result["kelly"]
    voltarget = result["voltarget"]

    print("\n" + "-"*70)
    print("KELLY (Fractional-Kernel) SCHEME")
    print("-"*70)
    print(f"  Trade count:      {kelly['trade_count']}")
    print(f"  Total PnL:        ${kelly['total_pnl']:.2f}")
    print(f"  Mean PnL/trade:   ${kelly['mean_pnl']:.2f}")
    print(f"  Max single loss:  ${kelly['max_loss']:.2f}")

    print("\n" + "-"*70)
    print("VOL-TARGET SCHEME (Shadow)")
    print("-"*70)
    print(f"  Trade count:      {voltarget['trade_count']}")
    print(f"  Total PnL:        ${voltarget['total_pnl']:.2f}")
    print(f"  Mean PnL/trade:   ${voltarget['mean_pnl']:.2f}")
    print(f"  Max single loss:  ${voltarget['max_loss']:.2f}")

    print("\n" + "-"*70)
    print("DELTA (Vol-Target vs Kelly)")
    print("-"*70)
    delta_pnl = voltarget['total_pnl'] - kelly['total_pnl']
    delta_mean = voltarget['mean_pnl'] - kelly['mean_pnl']
    delta_loss = voltarget['max_loss'] - kelly['max_loss']  # less negative = better
    print(f"  Total PnL delta:  ${delta_pnl:+.2f}")
    print(f"  Mean PnL delta:   ${delta_mean:+.2f}")
    print(f"  Max loss delta:   ${delta_loss:+.2f}")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
